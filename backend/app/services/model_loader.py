"""本地模型的加载与进程级缓存。

为什么需要进程级缓存：bge-m3 权重约 2.2GB，加载一次约 2.6 秒、占用大量内存。
如果每个请求都新建一个实例，服务会在几秒内被拖垮。因此本地模型在整个进程内
只加载一份，所有用户共享（`README.md` 第 3.5 节的设计意图）。

远程模型（provider=qwen）不走这里，它们按用户配置轻量创建。
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

# 本地模型实例缓存。用锁保护：FastAPI 在线程池里处理请求，
# 两个并发请求可能同时触发首次加载，不加锁会加载出两份模型并Double占用内存。
_lock = threading.Lock()
_local_embedding: Any | None = None
_local_reranker: Any | None = None


def _resolve_device(configured: str, *, force_cpu: bool = False) -> str:
    """把配置里的设备取值解析为实际可用的设备名。

    `auto` 会检测 CUDA 是否真的可用。这里**不**在显式配置 `cuda` 时静默降级：
    用户明确写了 cuda 就是期望用 GPU，如果环境不支持应当直接报错，
    否则会出现「以为在用 GPU，实际一直在跑 CPU」这种极难排查的情况。
    """
    if force_cpu:
        return "cpu"

    value = (configured or "auto").strip().lower()
    if value == "cpu":
        return "cpu"

    try:
        import torch
    except ImportError:
        if value == "cuda":
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "配置要求使用 CUDA，但当前环境未安装 torch",
            ) from None
        return "cpu"

    cuda_available = bool(torch.cuda.is_available())

    if value == "cuda":
        if not cuda_available:
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "配置要求 EMBED_DEVICE/RERANK_DEVICE=cuda，但当前 torch 无法使用 CUDA"
                f"（torch {torch.__version__}）。请改用 auto 或 cpu，"
                "或安装 CUDA 版 torch 后重试。",
            )
        return "cuda"

    if value == "auto":
        return "cuda" if cuda_available else "cpu"

    raise AppError(ErrorCode.MODEL_CONFIG_INVALID, f"不支持的设备取值：{configured}")


def get_local_embedding() -> Any:
    """返回进程级共享的本地 Embedding 实例。"""
    global _local_embedding
    if _local_embedding is not None:
        return _local_embedding

    with _lock:
        if _local_embedding is not None:
            return _local_embedding

        settings = get_settings()
        model_path = settings.local_bge_m3_path.strip()
        if not model_path:
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "未配置本地 Embedding 模型路径（LOCAL_BGE_M3_PATH）",
            )

        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        device = _resolve_device(settings.embed_device)
        logger.info("加载本地 Embedding 模型 path=%s device=%s", model_path, device)
        try:
            _local_embedding = HuggingFaceEmbedding(model_name=model_path, device=device)
        except Exception as exc:
            # GPU 加载失败（显存不足、驱动不匹配等）时回落到 CPU 重试一次。
            # 这比直接报错更实用：用户仍然能完成索引构建，只是慢一些。
            if device == "cuda":
                logger.warning(
                    "GPU 加载 Embedding 失败，回落 CPU 重试：%s: %s",
                    type(exc).__name__,
                    str(exc)[:200],
                )
                _local_embedding = HuggingFaceEmbedding(model_name=model_path, device="cpu")
            else:
                logger.exception("加载本地 Embedding 模型失败")
                raise AppError(
                    ErrorCode.MODEL_CONFIG_INVALID,
                    f"加载本地 Embedding 模型失败：{type(exc).__name__}。"
                    "请确认 LOCAL_BGE_M3_PATH 指向的目录里有 config.json"
                    "（部分模型的权重位于 snapshots/<分支> 子目录下）。",
                ) from exc

        logger.info("本地 Embedding 模型加载完成 device=%s", device)
        return _local_embedding


def get_local_reranker() -> Any:
    """返回进程级共享的本地 Reranker 实例。"""
    global _local_reranker
    if _local_reranker is not None:
        return _local_reranker

    with _lock:
        if _local_reranker is not None:
            return _local_reranker

        settings = get_settings()
        model_path = settings.local_bge_reranker_path.strip()
        if not model_path:
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "未配置本地 Reranker 模型路径（LOCAL_BGE_RERANKER_PATH）",
            )

        from sentence_transformers import CrossEncoder

        device = _resolve_device(settings.rerank_device)
        logger.info("加载本地 Reranker 模型 path=%s device=%s", model_path, device)
        try:
            _local_reranker = CrossEncoder(model_path, max_length=512, device=device)
        except Exception as exc:
            if device == "cuda":
                logger.warning(
                    "GPU 加载 Reranker 失败，回落 CPU 重试：%s: %s",
                    type(exc).__name__,
                    str(exc)[:200],
                )
                _local_reranker = CrossEncoder(model_path, max_length=512, device="cpu")
            else:
                logger.exception("加载本地 Reranker 模型失败")
                raise AppError(
                    ErrorCode.MODEL_CONFIG_INVALID,
                    f"加载本地 Reranker 模型失败：{type(exc).__name__}",
                ) from exc

        logger.info("本地 Reranker 模型加载完成 device=%s", device)
        return _local_reranker


def reset_model_cache() -> None:
    """清空缓存，释放内存。

    模型配置变更后由 config_service 调用：换了 Embedding 模型却继续用旧实例，
    会产出与新索引版本不匹配的向量。
    """
    global _local_embedding, _local_reranker
    with _lock:
        _local_embedding = None
        _local_reranker = None
    logger.info("已清空本地模型缓存")
