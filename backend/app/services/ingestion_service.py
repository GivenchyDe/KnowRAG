"""文档摄取服务：解析 → 切块 → 向量化 → 写入向量库与文档存储。

执行模型说明（偏离设计文档，见 `docs/DESIGN_IMPLEMENTATION.md` Phase 3 状态）：
设计文档建议初期用 FastAPI `BackgroundTasks`。这里改用**进程内线程池**，
原因是 `BackgroundTasks` 依附于单次 HTTP 请求生命周期，无法承载
「重建索引时批量重跑全部文档」这类没有请求上下文的场景，
也没有并发上限控制（同时上传 10 个文件会起 10 个后台任务）。
线程池两者都能解决，且 Phase 6 换成独立 worker 进程时只需替换 `enqueue` 的实现。

任务状态与进度写入数据库，前端按 task_id 轮询，因此进程重启前已提交的任务
会停留在 running 状态——`reap_stale_tasks()` 在启动时把它们标记为失败，
避免任务永久卡住。
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.db.base import utc_now
from app.db.session import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.ingestion_task import IngestionStatus, IngestionTask
from app.models.model_config import ModelConfig
from app.rag import chunking, docstore, loaders
from app.services import index_service, vector_service

logger = get_logger(__name__)

# 并发上限：embedding 是 CPU/GPU 密集型，同时跑太多任务会互相拖慢，
# 而每个任务内部已按批处理，因此 2 个并发足够，又不会让内存爆掉。
_MAX_WORKERS = 2
# 单次写入向量库的批量。太大内存占用高，太小则往返次数多。
_EMBED_BATCH = 32

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()

# 进度节点。用常量而不是散落的魔数，便于以后调整阶段划分。
_PROGRESS_PARSING = 10
_PROGRESS_CHUNKING = 30
_PROGRESS_EMBEDDING = 60
_PROGRESS_STORING = 85
_PROGRESS_DONE = 100


def _get_executor() -> ThreadPoolExecutor:
    """懒加载线程池。

    不在模块导入时创建：那样即使用不到摄取功能也会常驻线程，
    并且在 fork 型部署（gunicorn preload）下会得到失效的线程池。
    """
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="ingest")
            logger.info("摄取线程池已创建 max_workers=%d", _MAX_WORKERS)
        return _executor


def shutdown_executor() -> None:
    """关闭线程池，供应用退出时调用。"""
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None
            logger.info("摄取线程池已关闭")


# --------------------------------------------------------------------------- #
# 任务记录
# --------------------------------------------------------------------------- #


def create_task(db: Session, *, user_id: int, document_id: int) -> IngestionTask:
    """创建摄取任务记录。"""
    task = IngestionTask(
        task_id=str(uuid.uuid4()),
        user_id=user_id,
        document_id=document_id,
        status=IngestionStatus.PENDING,
        progress=0,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, user_id: int, task_id: str) -> IngestionTask:
    """按 task_id 查任务，且必须属于当前用户。

    不带 user_id 过滤就返回任务状态，会让任何人凭一个 UUID 猜出别人的
    文档名、失败原因与处理进度。
    """
    task = db.scalar(
        select(IngestionTask).where(
            IngestionTask.task_id == task_id, IngestionTask.user_id == user_id
        )
    )
    if task is None:
        raise AppError(ErrorCode.RESOURCE_NOT_FOUND, "任务不存在")
    return task


def enqueue(db: Session, task: IngestionTask) -> None:
    """把任务提交到线程池。

    只传 task_id 而不是 ORM 对象：ORM 对象绑定在请求的 Session 上，
    请求结束会话就关闭了，跨线程使用会抛 DetachedInstanceError。
    后台线程自己开一个 Session 重新读取（`_run_task`）。
    """
    task_id = task.task_id
    _get_executor().submit(_run_task, task_id)
    logger.info("摄取任务已入队 task_id=%s document_id=%s", task_id, task.document_id)


def reap_stale_tasks() -> int:
    """把上次进程退出时残留的 pending / running 任务标记为失败。

    进程崩溃或重启后，线程池里的任务不会继续执行，但数据库里仍是 running。
    不清理的话前端会一直轮询一个永远不会推进的任务。
    """
    db = SessionLocal()
    try:
        stale = db.scalars(
            select(IngestionTask).where(
                IngestionTask.status.in_([IngestionStatus.PENDING, IngestionStatus.RUNNING])
            )
        ).all()
        for task in stale:
            task.status = IngestionStatus.FAILED
            task.error = "服务重启导致任务中断，请重新上传或重建索引"
            task.finished_at = utc_now()
        if stale:
            db.commit()
            logger.warning("已把 %d 个残留任务标记为失败", len(stale))
        return len(stale)
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 任务执行
# --------------------------------------------------------------------------- #


def _update(db: Session, task: IngestionTask, *, status: str, progress: int, error: str | None = None) -> None:
    """更新任务状态并提交。"""
    task.status = status
    task.progress = progress
    if error is not None:
        task.error = error
    db.commit()


def _run_task(task_id: str) -> None:
    """后台线程入口：独立 Session、独立事务。"""
    db = SessionLocal()
    try:
        task = db.scalar(select(IngestionTask).where(IngestionTask.task_id == task_id))
        if task is None:
            logger.warning("任务不存在，跳过 task_id=%s", task_id)
            return

        document = db.get(Document, task.document_id)
        if document is None:
            _update(db, task, status=IngestionStatus.FAILED, progress=0, error="文档记录已不存在")
            return

        task.status = IngestionStatus.RUNNING
        task.started_at = utc_now()
        task.progress = 0
        task.error = None
        db.commit()

        try:
            _ingest(db, task, document)
        except AppError as exc:
            # 可预期的业务失败：把 message 直接展示给用户。
            logger.warning("摄取失败 task_id=%s code=%s message=%s", task_id, exc.code, exc.message)
            document.status = DocumentStatus.FAILED
            _update(db, task, status=IngestionStatus.FAILED, progress=task.progress, error=exc.message)
        except Exception as exc:
            # 非预期异常：只记类型，不把堆栈或内部细节暴露给前端。
            logger.exception("摄取异常 task_id=%s error=%s", task_id, type(exc).__name__)
            document.status = DocumentStatus.FAILED
            _update(
                db,
                task,
                status=IngestionStatus.FAILED,
                progress=task.progress,
                error=f"处理文档时发生内部错误（{type(exc).__name__}）",
            )
    finally:
        db.close()


def _ingest(db: Session, task: IngestionTask, document: Document) -> None:
    """摄取主流程。"""
    from app.services import config_service

    config: ModelConfig = config_service.get_or_create_config(db)
    settings = get_settings()

    # 1) 解析
    _update(db, task, status=IngestionStatus.RUNNING, progress=_PROGRESS_PARSING)
    path = Path(document.stored_path)
    if not path.exists():
        raise AppError(ErrorCode.INGESTION_FAILED, "原始文件已丢失，请重新上传")
    text = loaders.extract_text(path)
    logger.info(
        "解析完成 document_id=%s chars=%d fingerprint=%s",
        document.id,
        len(text),
        chunking.text_fingerprint(text),
    )

    # 2) 确认索引版本
    index = index_service.ensure_index(db, document.user_id, config)

    # 3) 切块
    _update(db, task, status=IngestionStatus.RUNNING, progress=_PROGRESS_CHUNKING)
    chunks = chunking.split_text(
        text,
        document_id=document.id,
        user_id=document.user_id,
        filename=document.filename,
        index_version=index.index_version,
        chunk_size=index.chunk_size,
        chunk_overlap=index.chunk_overlap,
    )
    if not chunks:
        raise AppError(ErrorCode.INGESTION_FAILED, "切块结果为空，文档可能没有可索引内容")

    # 4) 向量化
    _update(db, task, status=IngestionStatus.RUNNING, progress=_PROGRESS_EMBEDDING)
    embedding = _build_embedding(config)
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        vectors.extend(embedding.get_text_embedding_batch([c.text for c in batch]))
    if len(vectors) != len(chunks):
        raise AppError(
            ErrorCode.INGESTION_FAILED,
            f"向量数量与切片数量不一致（{len(vectors)} != {len(chunks)}）",
        )

    # 维度校验：写错维度的向量会在 Chroma 里报错，但错误信息晦涩，
    # 这里提前给出可读提示（配置里的 embed_dimension 必须与模型实际输出一致）。
    actual_dimension = len(vectors[0])
    if actual_dimension != index.embedding_dimension:
        raise AppError(
            ErrorCode.MODEL_CONFIG_INVALID,
            f"向量维度与配置不一致：模型实际输出 {actual_dimension} 维，"
            f"而配置的向量维度为 {index.embedding_dimension}。请到模型设置页修正后重建索引。",
        )

    # 5) 写入向量库与文档存储
    _update(db, task, status=IngestionStatus.RUNNING, progress=_PROGRESS_STORING)
    # 重建/重复摄取时先清掉该文档的旧切片，避免残留上一版本的向量。
    vector_service.delete_by_document(index.collection_name, document.id)
    vector_service.upsert_chunks(
        index.collection_name,
        ids=[c.chunk_id for c in chunks],
        embeddings=vectors,
        documents=[c.text for c in chunks],
        metadatas=[c.metadata for c in chunks],
    )
    docstore.put_nodes(document.user_id, _build_nodes(chunks))

    # 6) 收尾
    document.status = DocumentStatus.INDEXED
    index_service.mark_ready(db, index)
    task.finished_at = utc_now()
    _update(db, task, status=IngestionStatus.SUCCESS, progress=_PROGRESS_DONE)

    logger.info(
        "摄取成功 task_id=%s document_id=%s chunks=%d collection=%s",
        task.task_id,
        document.id,
        len(chunks),
        index.collection_name,
    )


def _build_embedding(config: ModelConfig):
    """按当前配置构造 Embedding 实例。

    远程 provider 每次调用都新建（轻量、无状态）；
    本地 provider 走进程级缓存（模型加载昂贵，必须共享）。
    """
    if config.embed_provider == "local":
        from app.services.model_loader import get_local_embedding

        return get_local_embedding()

    if config.embed_provider == "qwen":
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        from app.services.crypto_service import decrypt_api_key

        if not config.embed_api_key_encrypted:
            raise AppError(
                ErrorCode.MODEL_CONFIG_INVALID,
                "Embedding provider 为 qwen，但尚未填写 Embedding API Key",
            )
        return DashScopeEmbedding(
            model_name=config.embed_model or "text-embedding-v4",
            api_key=decrypt_api_key(config.embed_api_key_encrypted),
        )

    raise AppError(
        ErrorCode.MODEL_CONFIG_INVALID, f"不支持的 Embedding provider：{config.embed_provider}"
    )


def _build_nodes(chunks: list[chunking.Chunk]) -> list[object]:
    """把切片转换为 DocStore 的 TextNode。

    节点建立到所属文档的 `SOURCE` 关系，docstore 借此把同一文档的节点归组，
    删除文档时可以一次清干净（`delete_ref_doc`）。
    """
    from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

    nodes: list[object] = []
    for chunk in chunks:
        document_id = int(str(chunk.metadata["document_id"]))
        nodes.append(
            TextNode(
                id_=chunk.chunk_id,
                text=chunk.text,
                metadata=dict(chunk.metadata),
                relationships={
                    NodeRelationship.SOURCE: RelatedNodeInfo(node_id=str(document_id))
                },
            )
        )
    return nodes


def enqueue_rebuild(db: Session, *, user_id: int) -> IngestionTask | None:
    """为某用户的全部有效文档重新创建摄取任务，返回最后一个任务。

    返回 None 表示该用户没有任何可索引文档（前端据此提示「请先上传文档」）。
    """
    documents = [
        d
        for d in db.scalars(
            select(Document).where(
                Document.user_id == user_id, Document.status != DocumentStatus.DELETED
            )
        ).all()
    ]
    if not documents:
        return None

    last_task: IngestionTask | None = None
    for document in documents:
        # 重建时先把文档状态置回 uploaded，避免重建过程中列表仍显示「已索引」。
        document.status = DocumentStatus.UPLOADED
        task = create_task(db, user_id=user_id, document_id=document.id)
        enqueue(db, task)
        last_task = task
    logger.info("用户 %s 的索引重建已入队，文档数=%d", user_id, len(documents))
    return last_task


def summarize_documents(db: Session, user_id: int) -> dict[str, int]:
    """文档状态统计，供文档页展示概览。"""
    documents = list(
        db.scalars(select(Document).where(Document.user_id == user_id)).all()
    )
    summary = {status.value: 0 for status in DocumentStatus}
    for document in documents:
        summary[document.status] = summary.get(document.status, 0) + 1
    summary["total"] = len(documents)
    return summary
