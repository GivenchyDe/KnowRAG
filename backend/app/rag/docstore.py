"""DocStore：把切块后的文档节点持久化到 MongoDB。

为什么需要它：Chroma 只存向量与原文，缺少「按 chunk_id 取回完整节点」的能力。
重建索引、增量更新、引用原文回显都要用到节点本身，把这些塞进向量库会让
向量库承担它不擅长的职责。

隔离方式：每个用户一个 **namespace**（`user_{user_id}`），而不是每个用户一个数据库。
`MongoDocumentStore` 支持 namespace 参数，同一 MongoDB 库内通过不同的集合后缀隔离。
这样既满足用户隔离，又不需要为每个用户新建数据库。
数据库为 `knowrag`，与本机既有的 `llama_index`、`llama_md_report` 库完全隔离。
"""

from __future__ import annotations

import threading
from typing import Any

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
# 按 namespace 缓存实例，避免每次调用都重建 KVStore（每次重建都会新建 MongoClient）。
_stores: dict[str, Any] = {}


def reset() -> None:
    """丢弃缓存的实例。模型/存储配置变更或测试时使用。"""
    with _lock:
        _stores.clear()
    logger.info("已清空 DocStore 缓存")


def _namespace_of(user_id: int) -> str:
    """用户对应的 namespace。"""
    return f"user_{user_id}"


def get_docstore(user_id: int) -> Any:
    """返回该用户的 DocStore 实例（进程级缓存）。"""
    namespace = _namespace_of(user_id)
    cached = _stores.get(namespace)
    if cached is not None:
        return cached

    with _lock:
        cached = _stores.get(namespace)
        if cached is not None:
            return cached

        settings = get_settings()
        try:
            from llama_index.storage.docstore.mongodb import MongoDocumentStore

            store = MongoDocumentStore.from_host_and_port(
                host=settings.mongodb_url,
                port=None,
                db_name=settings.mongodb_db,
                namespace=namespace,
            )
        except Exception as exc:
            # 不在这里吞异常：调用方（摄取流程）需要把失败原因写进任务记录，
            # 让用户在前端看到「无法连接文档存储」而不是一个静默卡住的任务。
            raise AppError(
                ErrorCode.INGESTION_FAILED,
                f"无法连接文档存储（MongoDB）: {type(exc).__name__}。请确认 MongoDB 服务已启动。",
            ) from exc

        _stores[namespace] = store
        logger.info("初始化 DocStore namespace=%s db=%s", namespace, settings.mongodb_db)
        return store


def put_nodes(user_id: int, nodes: list[Any]) -> None:
    """写入或覆盖节点。按 node_id 幂等，重复摄取不会产生重复数据。"""
    if not nodes:
        return
    store = get_docstore(user_id)
    try:
        store.add_documents(nodes, allow_update=True)
    except Exception as exc:
        raise AppError(
            ErrorCode.INGESTION_FAILED, f"写入文档存储失败：{type(exc).__name__}"
        ) from exc


def delete_by_document(user_id: int, document_id: int) -> None:
    """删除某文档在 DocStore 中的全部节点。

    以 `ref_doc_id` 为单位删除：节点创建时通过 `relationships` 指向所属文档，
    docstore 借此把同一文档的节点归为一组，一次调用即可全部清掉。

    `raise_error=False` 让「本来就没有数据」不报错——删除应当幂等，
    调用方不需要先查询是否存在。
    """
    store = get_docstore(user_id)
    try:
        store.delete_ref_doc(str(document_id), raise_error=False)
    except Exception as exc:
        # 删除失败只告警不阻断：向量已经删掉了，DocStore 残留属于可清理的垃圾数据，
        # 不应该让用户看到「删除文档失败」却发现列表里已经没有这条记录。
        logger.warning(
            "DocStore 删除文档节点失败 document_id=%s error=%s",
            document_id,
            type(exc).__name__,
        )


def describe(user_id: int) -> dict[str, Any]:
    """返回 DocStore 状态，供索引状态接口展示。"""
    settings = get_settings()
    info: dict[str, Any] = {
        "url": settings.mongodb_url,
        "db": settings.mongodb_db,
        "namespace": _namespace_of(user_id),
        "available": True,
    }
    try:
        store = get_docstore(user_id)
        nodes = store.get_all_ref_doc_info() or {}
        info["ref_doc_count"] = len(nodes)
    except Exception as exc:
        info["available"] = False
        info["error"] = type(exc).__name__
    return info
