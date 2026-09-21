"""索引状态与重建路由。

路径规范：`/api/index/...`（`docs/CODING_CONVENTIONS.md` 第 6.1 节）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.knowledge_base_index import IndexStatus
from app.models.user import User
from app.rag import docstore
from app.schemas.documents import IndexStatusResponse, RebuildResponse
from app.security.dependencies import get_current_active_user
from app.services import config_service, index_service, ingestion_service, vector_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/index", tags=["index"])


def _build_status_message(
    *, status: IndexStatus, embedding_changed: bool, document_count: int, has_index: bool
) -> str:
    """生成给用户看的一句话说明。

    前端只负责展示这段文案，不自己拼提示语——否则同一种状态在两个地方
    各写一套措辞，早晚会不一致。
    """
    if document_count == 0:
        return "尚未上传任何文档，请先上传文档后再构建索引"
    if not has_index:
        return "索引尚未构建，请点击「重建索引」开始构建"
    if embedding_changed:
        return "Embedding 配置已变更，向量空间不匹配，需要重建索引"
    if status == IndexStatus.BUILDING:
        return "索引正在构建中，完成后即可用于问答"
    if status == IndexStatus.FAILED:
        return "上次索引构建失败，请重建索引"
    if status == IndexStatus.STALE:
        return "索引已过期，需要重建索引"
    return "索引可用"


@router.get("/status", response_model=IndexStatusResponse, summary="查询索引状态")
def read_index_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> IndexStatusResponse:
    """返回当前用户的知识库索引状态。"""
    settings = get_settings()
    config = config_service.get_or_create_config(db)
    index = index_service.get_latest_index(db, current_user.id)

    summary = ingestion_service.summarize_documents(db, current_user.id)
    # 只统计真正进入向量库的文档（status=indexed），
    # failed / uploaded 的文档不在向量库内，算进来会让用户误以为索引里有内容。
    document_count = summary.get("indexed", 0)

    embedding_changed = index is not None and index_service.signature_changed(index, config)

    if index is None:
        # 没有索引记录时对外报 stale（= 不可用于问答）。不报 building：
        # building 意味着「有任务正在推进」，而这里可能只是从未构建过，
        # 前端据此展示的动作（等待 vs 立即重建）完全不同。
        return IndexStatusResponse(
            status=IndexStatus.STALE,
            collection_name=None,
            index_version=None,
            embedding_model=config.embed_model,
            embedding_dimension=config.embed_dimension,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            document_count=document_count,
            message=_build_status_message(
                status=IndexStatus.STALE,
                embedding_changed=False,
                document_count=document_count,
                has_index=False,
            ),
            vector_store=vector_service.describe(),
            doc_store=docstore.describe(current_user.id),
        )

    # 状态对外统一：配置不匹配时无论库里记的是什么都报 stale，
    # 这样前端只需判断一个字段，不必自己再比对配置。
    effective_status = IndexStatus.STALE if embedding_changed else IndexStatus(index.status)

    # 没有任何已索引文档时，索引记录即使存的是 ready 也不可信
    # （例如文档全部被删除后，集合里已经空了）。
    # 不修正的话会出现「status=ready 但 message=请先上传文档」这种自相矛盾的响应，
    # 前端会据此显示「索引可用」，误导用户。
    if document_count == 0 and effective_status == IndexStatus.READY:
        effective_status = IndexStatus.STALE

    return IndexStatusResponse(
        status=effective_status,
        collection_name=index.collection_name,
        index_version=index.index_version,
        embedding_model=index.embedding_model,
        embedding_dimension=index.embedding_dimension,
        chunk_size=index.chunk_size,
        chunk_overlap=index.chunk_overlap,
        document_count=document_count,
        message=_build_status_message(
            status=effective_status,
            embedding_changed=embedding_changed,
            document_count=document_count,
            has_index=True,
        ),
        vector_store=vector_service.describe(),
        doc_store=docstore.describe(current_user.id),
    )


@router.post("/rebuild", response_model=RebuildResponse, summary="重建知识库索引")
def rebuild_index(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> RebuildResponse:
    """为当前用户的所有文档重新构建索引。

    实现方式：为每个文档创建一个新的摄取任务。`ensure_index` 会新建一个
    版本号更高的索引记录（因为用户的旧索引在配置变更后已不可用），
    每个文档写完后都会调用 `mark_ready`，同一用户只保留一个 ready 索引。
    """
    task = ingestion_service.enqueue_rebuild(db, user_id=current_user.id)
    summary = ingestion_service.summarize_documents(db, current_user.id)
    document_count = summary.get("indexed", 0) + summary.get("uploaded", 0) + summary.get("failed", 0)

    if task is None:
        return RebuildResponse(
            task_id=None,
            status="skipped",
            message="没有可索引的文档，请先上传文档",
            document_count=0,
        )

    logger.info(
        "已触发索引重建 user_id=%s 文档数=%d 首个任务=%s",
        current_user.id,
        document_count,
        task.task_id,
    )
    return RebuildResponse(
        task_id=task.task_id,
        status=task.status,
        message=f"已开始重建索引，共 {document_count} 个文档，请在文档页查看进度",
        document_count=document_count,
    )
