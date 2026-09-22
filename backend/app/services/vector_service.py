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
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_client: Any | None = None

# 连接失败后的重试冷却（秒）。
#
# 失败后**不能永久放弃**：Chroma 是独立进程，比后端晚启动或中途重启都是常态，
# 一次失败就永久失效意味着用户必须重启后端（连带丢掉会话缓存与已加载模型）。
# 也不能每次请求都重试：每次建连都带内部重试、耗时数秒，
# 前端轮询索引状态时会让每个请求都卡住几秒。
# 15 秒是「用户等待可接受」与「不给不可用的服务叠加压力」的折中。
_RETRY_COOLDOWN_SECONDS = 15.0
_last_failure_at: float | None = None
_LAST_FAILURE_MESSAGE = ""


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
    """返回进程级共享的 Chroma 客户端。首次调用时才真正建立连接。

    失败后会按冷却间隔重试，而不是永久放弃：Chroma 是个独立进程，
    它比后端晚启动、或中途重启都是常态。若连接失败一次就再也不重试，
    用户必须重启后端才能恢复，而重启后端会连带丢掉会话缓存与已加载的模型。
    """
    # global 声明必须在函数体最前面：Python 要求它在任何对该名字的**使用**之前出现，
    # 放在 except 块里会直接报 SyntaxError（name is used prior to global declaration）。
    global _client, _last_failure_at, _LAST_FAILURE_MESSAGE
    if _client is not None:
        return _client

    with _lock:
        if _client is not None:
            return _client
        # 冷却期检查必须在锁内做：多个并发请求同时发现 Chroma 不可用时，
        # 不加这层判断会各自发起一次建连（每次都带重试，耗时数秒），
        # 反而给已经不可用的服务叠加上百次无谓请求。
        now = time.monotonic()
        if _last_failure_at is not None and (now - _last_failure_at) < _RETRY_COOLDOWN_SECONDS:
            raise VectorStoreUnavailableError(_LAST_FAILURE_MESSAGE)

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
            # 记录失败时刻，启动冷却期；同时记下文案供冷却期内的请求复用。
            _last_failure_at = time.monotonic()
            if mode == "server":
                _LAST_FAILURE_MESSAGE = (
                    "无法连接向量库服务。请确认 Chroma 已启动："
                    f"chroma run --host {settings.chroma_host} --port {settings.chroma_port}"
                )
            else:
                _LAST_FAILURE_MESSAGE = f"初始化向量库失败：{type(exc).__name__}"
            logger.warning("向量库连接失败（%.0f 秒内不再重试）：%s", _RETRY_COOLDOWN_SECONDS, exc)
            raise VectorStoreUnavailableError(_LAST_FAILURE_MESSAGE) from exc

        _client = client
        _last_failure_at = None
        return _client


def reset_client() -> None:
    """丢弃缓存的客户端，下次调用会重新建连。测试与配置变更时使用。"""
    global _client, _last_failure_at, _LAST_FAILURE_MESSAGE
    with _lock:
        _client = None
        _last_failure_at = None
        _LAST_FAILURE_MESSAGE = ""


def get_or_create_collection(name: str) -> Any:
    """获取或创建集合。

    距离度量固定为 cosine：bge-m3 输出已归一化（模型自带 Normalize 模块），
    余弦距离在这种情况下语义最稳定，且与维度无关。
    """
    client = get_chroma_client()
    try:
        return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})
    except Exception as exc:
        # 异常类型只进日志，不进给用户的 message：ConnectError / HTTPStatusError
        # 这类内部名称对用户没有意义，反而会掩盖真正可操作的信息。
        logger.warning("获取向量集合失败 name=%s error=%s", name, type(exc).__name__)
        raise VectorStoreUnavailableError("向量库暂时不可用，请稍后重试") from exc


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
        logger.warning("写入向量库失败 collection=%s error=%s", collection_name, type(exc).__name__)
        raise VectorStoreUnavailableError("写入向量库失败，请稍后重试") from exc


def delete_by_document(collection_name: str, document_id: int) -> None:
    """删除某文档的所有切片。

    使用 metadata 过滤删除，而不是按 chunk_id 前缀猜：
    chunk_id 的拼接规则一旦调整，前缀匹配就会失效并留下孤儿数据。
    """
    collection = get_or_create_collection(collection_name)
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as exc:
        logger.warning("删除向量失败 collection=%s error=%s", collection_name, type(exc).__name__)
        raise VectorStoreUnavailableError("删除向量失败，请稍后重试") from exc


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
        logger.warning("向量检索失败 collection=%s error=%s", collection_name, type(exc).__name__)
        raise VectorStoreUnavailableError("向量检索失败，请稍后重试") from exc


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
