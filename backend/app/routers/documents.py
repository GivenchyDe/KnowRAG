"""文档管理与摄取任务路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：文档接口挂在 `/api/docs/...`。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.document import DocumentStatus
from app.models.user import User
from app.rag import docstore, loaders
from app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentListResponse,
    DocumentResponse,
    TaskResponse,
    UploadResponse,
)
from app.security.dependencies import get_current_active_user
from app.services import document_service, index_service, ingestion_service, vector_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED, summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> UploadResponse:
    """上传文档并创建异步摄取任务。

    返回 202 而不是 201：文档记录已创建，但索引尚未构建完成，
    真正的结果要通过 `GET /api/docs/tasks/{task_id}` 轮询。
    """
    filename = file.filename or "unnamed"
    if not loaders.is_supported(filename):
        raise loaders.UnsupportedFileTypeError(filename)

    # 先按块读入并累计大小，超过上限立即中断，不把超大文件整个读进内存。
    # 用流式读取而不是 await file.read() 一次读完：后者在超大文件上会直接把内存打满，
    # 而限制本应在上传过程中生效，而不是读完之后才发现。
    chunks: list[bytes] = []
    total = 0
    limit = get_settings().max_upload_bytes
    while True:
        block = await file.read(1024 * 1024)
        if not block:
            break
        total += len(block)
        if total > limit:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                f"文件过大，上限为 {limit / 1024 / 1024:.0f}MB",
            )
        chunks.append(block)
    content = b"".join(chunks)

    stored = document_service.save_upload(current_user.id, filename, content)

    # 同用户内容去重：重复上传会白耗算力并在检索时人为抬高该文档的权重。
    duplicate = document_service.find_duplicate(db, current_user.id, stored.sha256)
    if duplicate is not None:
        # 已经在磁盘上写了新副本，去重命中时要把它删掉，否则会留下孤儿文件。
        stored.path.unlink(missing_ok=True)
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            f"该文件内容与已有文档「{duplicate.filename}」完全相同，无需重复上传",
        )

    document = document_service.create_document(
        db, user_id=current_user.id, original_filename=filename, stored=stored
    )
    task = ingestion_service.create_task(
        db, user_id=current_user.id, document_id=document.id
    )
    ingestion_service.enqueue(db, task)

    return UploadResponse(
        document_id=document.id,
        task_id=task.task_id,
        status=task.status,
        filename=document.filename,
        size_bytes=document.size_bytes,
    )


@router.get("", response_model=DocumentListResponse, summary="文档列表")
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DocumentListResponse:
    """列出当前用户的文档。分页参数统一为 `page` / `page_size`。"""
    documents = document_service.list_documents(db, current_user.id)
    total = len(documents)
    start = (page - 1) * page_size
    page_items = documents[start : start + page_size]

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(item) for item in page_items],
        total=total,
        page=page,
        page_size=page_size,
        status_summary=ingestion_service.summarize_documents(db, current_user.id),
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse, summary="查询摄取任务状态")
def read_task(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TaskResponse:
    """按 task_id 查询任务进度。仅能查询自己的任务。"""
    task = ingestion_service.get_task(db, current_user.id, task_id)
    return TaskResponse.model_validate(task)


@router.delete("/{document_id}", response_model=DeleteDocumentResponse, summary="删除文档")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DeleteDocumentResponse:
    """删除文档及其向量与文档存储中的节点。

    删除顺序：先清向量与节点，再改数据库状态。反过来做的话，
    如果清向量失败，数据库已标记删除，用户会看到列表里没了但检索仍能命中，
    这种不一致极难排查。
    """
    document = document_service.get_document(db, current_user.id, document_id)

    index = index_service.get_latest_index(db, current_user.id)
    if index is not None:
        try:
            vector_service.delete_by_document(index.collection_name, document.id)
        except AppError as exc:
            # 向量库不可用时仍然允许删除文档记录，否则用户会被卡住无法清理列表。
            # 但必须记日志，让残留情况有迹可循。
            logger.warning(
                "删除文档时清理向量失败 document_id=%s error=%s", document.id, exc.message
            )
    docstore.delete_by_document(current_user.id, document.id)

    document.status = DocumentStatus.DELETED
    db.commit()
    document_service.remove_stored_file(document)

    logger.info("文档已删除 user_id=%s document_id=%s", current_user.id, document.id)
    return DeleteDocumentResponse(
        message=f"文档「{document.filename}」已删除", document_id=document.id
    )
