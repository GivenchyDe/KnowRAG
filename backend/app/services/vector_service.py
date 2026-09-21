"""Chroma 向量库访问层。

双模式（见 `config.py` 的 chroma_mode）：
- `server`：连接独立运行的 Chroma 服务，HTTP 通信；
- `embedded`：进程内直接读写本地 sqlite 文件，无需额外服务。

**懒加载**是这里的硬性要求：如果在导入或应用启动时就连接 Chroma，
那么 Chroma 没起来时整个后端都会启动失败——用户连登录页都打不开，
只能看到 500。推迟到真正使用向量库时（上传、检索）才连接，
才能给出「向量库不可用」这种可操作的提示。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_client: Any | None = None


class VectorStoreUnavailableError(AppError):
    """向量库不可用。

    单独定义是为了让调用方能区分「向量库连不上」与「索引还没建好」：
    前者是环境问题，后者是使用流程问题，给用户的提示完全不同。
    """

    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.INDEX_NOT_READY, message)


def _persist_dir() -> Path:
    """嵌入式模式的数据目录。"""
    settings = get_settings()
    configured = settings.chroma_persist_dir.strip()
    if configured:
        return Path(configured)
    # 默认放在 backend/file/chroma_db，与设计文档第 6 节的目录结构一致。
    backend_root = Path(__file__).resolve().parents[2]
    return backend_root / "file" / "chroma_db"


def get_chroma_client() -> Any:
    """返回进程级共享的 Chroma 客户端。首次调用时才真正建立连接。"""
    global _client
    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client

        settings = get_settings()
        mode = settings.chroma_mode.strip().lower()

        try:
            import chromadb

            if mode == "server":
                logger.info(
                    "连接 Chroma 服务 host=%s port=%s",
                    settings.chroma_host,
                    settings.chroma_port,
                )
                # 连接超时不在这里配置。
                #
                # 排查记录（避免后人重复踩坑）：
                # 曾经在此传入 chroma_server_http_timeout_seconds /
                # chroma_server_connect_timeout_seconds——这两个字段在本版本
                # （chromadb 1.5.9）的 Settings 里**并不存在**（实测被静默忽略），
                # 所以完全没有效果。本版本也没有可注入自定义 httpx client 的字段。
                #
                # 真正导致「Chroma 未启动时耗时约 5 秒且报 502」的原因是
                # **系统代理**：httpx 在 Windows 上读取注册表代理设置，
                # 把 127.0.0.1 也交给了代理。修复位于
                # `app/core/logging.py` 的 `_prepare_third_party_env()`
                # （设置 NO_PROXY 让本地地址直连），修复后耗时降到约 3.5 秒，
                # 且错误从误导性的 502 变成准确的「连接被拒绝」。
                # 剩余的建连重试耗时由 httpx 内部控制，本版本无法调整。
                client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port,
                )
                # 主动发一次心跳：HttpClient 的构造是惰性的，不探测的话
                # 连接失败会推迟到第一次写入时才暴露，错误位置更难定位。
                client.heartbeat()
            elif mode == "embedded":
                persist_dir = _persist_dir()
                persist_dir.mkdir(parents=True, exist_ok=True)
                logger.info("使用嵌入式 Chroma 目录=%s", persist_dir)
                client = chromadb.PersistentClient(path=str(persist_dir))
            else:
                raise VectorStoreUnavailableError(
                    f"不支持的 CHROMA_MODE：{settings.chroma_mode}（可选 server / embedded）"
                )
        except VectorStoreUnavailableError:
            raise
        except Exception as exc:
            if mode == "server":
                raise VectorStoreUnavailableError(
                    "无法连接向量库服务。请确认 Chroma 已启动："
                    f"chroma run --host {settings.chroma_host} --port {settings.chroma_port}"
                ) from exc
            raise VectorStoreUnavailableError(
                f"初始化向量库失败：{type(exc).__name__}"
            ) from exc

        _client = client
        return _client


def reset_client() -> None:
    """丢弃缓存的客户端。测试或多进程切换场景使用。"""
    global _client
    with _lock:
        _client = None


def get_or_create_collection(name: str) -> Any:
    """获取或创建集合。

    距离度量固定为 cosine：bge-m3 输出已归一化（模型自带 Normalize 模块），
    余弦距离在这种情况下语义最稳定，且与维度无关。
    """
    client = get_chroma_client()
    try:
        return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    except Exception as exc:
        raise VectorStoreUnavailableError(f"获取向量集合失败：{type(exc).__name__}") from exc


def delete_collection(name: str) -> None:
    """删除集合。

    集合不存在时 Chroma 会抛异常，这里吞掉——删除操作应当幂等，
    调用方（重建索引、删除用户数据）不需要先查询是否存在。
    """
    client = get_chroma_client()
    try:
        client.delete_collection(name)
        logger.info("已删除向量集合 %s", name)
    except Exception as exc:
        logger.warning("删除集合 %s 失败（可能不存在）：%s", name, type(exc).__name__)


def collection_count(name: str) -> int:
    """返回集合中的条目数。集合不存在时返回 0。"""
    try:
        return int(get_or_create_collection(name).count())
    except VectorStoreUnavailableError:
        raise
    except Exception:
        return 0


def upsert_chunks(
    collection_name: str,
    *,
    ids: list[str],
    embeddings: list[list[float]],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    """写入或覆盖向量条目。

    用 upsert 而不是 add：重建索引或重复摄取同一文档时，
    同样的 chunk_id 会被覆盖而不是产生重复条目，使摄取操作天然幂等。
    """
    if not ids:
        return
    collection = get_or_create_collection(collection_name)
    try:
        collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )
    except Exception as exc:
        raise VectorStoreUnavailableError(f"写入向量库失败：{type(exc).__name__}") from exc


def delete_by_document(collection_name: str, document_id: int) -> None:
    """删除某文档的所有切片。

    使用 metadata 过滤删除，而不是按 chunk_id 前缀猜：
    chunk_id 的拼接规则一旦调整，前缀匹配就会失效并留下孤儿数据。
    """
    collection = get_or_create_collection(collection_name)
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as exc:
        raise VectorStoreUnavailableError(f"删除向量失败：{type(exc).__name__}") from exc


def query_chunks(
    collection_name: str,
    *,
    query_embedding: list[float],
    top_k: int,
    user_id: int,
) -> dict[str, Any]:
    """按向量检索。

    `user_id` 过滤是**必须**的：即使集合已按用户命名，仍然加上 metadata 过滤，
    形成纵深防御——将来若有人把多个用户写入同一集合，隔离依然成立。
    """
    collection = get_or_create_collection(collection_name)
    try:
        return dict(
            collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"user_id": user_id},
                include=["documents", "metadatas", "distances"],
            )
        )
    except Exception as exc:
        raise VectorStoreUnavailableError(f"向量检索失败：{type(exc).__name__}") from exc


def describe() -> dict[str, Any]:
    """返回向量库当前形态，供索引状态接口展示与排查。"""
    settings = get_settings()
    info: dict[str, Any] = {
        "mode": settings.chroma_mode,
        "available": True,
        "collections": [],
    }
    try:
        client = get_chroma_client()
        info["collections"] = [c.name for c in client.list_collections()]
        if settings.chroma_mode == "server":
            info["version"] = client.get_version()
            info["endpoint"] = f"{settings.chroma_host}:{settings.chroma_port}"
        else:
            info["endpoint"] = str(_persist_dir())
    except VectorStoreUnavailableError as exc:
        info["available"] = False
        info["error"] = exc.message
    return info
