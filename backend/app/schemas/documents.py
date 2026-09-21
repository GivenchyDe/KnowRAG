"""文档与索引相关的请求体与响应体。

契约来源：`docs/DESIGN_IMPLEMENTATION.md` 第 6.3、6.4 节。
字段名与那里保持一致（如 `document_id` + `task_id`），前端类型再镜像一份。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus
from app.models.ingestion_task import IngestionStatus
from app.models.knowledge_base_index import IndexStatus


class DocumentResponse(BaseModel):
    """单个文档。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str | None
    size_bytes: int
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """文档列表。遵守 `docs/CODING_CONVENTIONS.md` 第 6.3 节的列表响应规范。"""

    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int
    # 各状态计数，前端用它渲染概览，避免再发一次请求
    status_summary: dict[str, int]


class UploadResponse(BaseModel):
    """上传响应。对应设计文档第 6.3 节的 `{document_id, task_id, status}`。"""

    document_id: int
    task_id: str
    status: str
    filename: str
    size_bytes: int


class TaskResponse(BaseModel):
    """摄取任务状态。对应设计文档第 6.3 节的 `{task_id, status, progress, error}`。"""

    model_config = ConfigDict(from_attributes=True)

    task_id: str
    document_id: int
    status: IngestionStatus
    progress: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


class RebuildResponse(BaseModel):
    """重建索引响应。对应设计文档第 6.4 节。"""

    # 用户没有任何文档时为 null，前端据此提示「请先上传文档」
    task_id: str | None
    status: str
    message: str
    document_count: int


class IndexStatusResponse(BaseModel):
    """索引状态。对应设计文档第 6.4 节。"""

    status: IndexStatus
    collection_name: str | None
    index_version: int | None
    embedding_model: str | None
    embedding_dimension: int | None
    chunk_size: int | None
    chunk_overlap: int | None
    document_count: int
    # 索引不可用时的可读原因，直接展示给用户
    message: str
    # 向量库与文档存储的连通性，便于用户排查「为什么索引建不起来」
    vector_store: dict[str, object]
    doc_store: dict[str, object]


class DeleteDocumentResponse(BaseModel):
    """删除文档响应。"""

    status: str = "success"
    message: str
    document_id: int


class PageQuery(BaseModel):
    """列表分页参数。参数名统一与 `docs/CODING_CONVENTIONS.md` 第 6.2 节一致。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
