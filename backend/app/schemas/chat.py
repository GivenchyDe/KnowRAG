"""问答相关请求体与响应体。

契约来源：`docs/DESIGN_IMPLEMENTATION.md` 第 6.5 节。
SSE 事件类型与 `docs/CODING_CONVENTIONS.md` 第 6.5 节一致：
`token` / `sources` / `complete` / `error`。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SourceItem(BaseModel):
    """一条引用来源。

    刻意不含 `stored_path` 等磁盘路径：那是服务端内部信息，
    暴露出去可用于探测目录结构。
    """

    document_id: int
    filename: str
    chunk_id: str
    score: float | None = None


class ChatStreamRequest(BaseModel):
    """流式问答请求，对应 POST /api/chat/stream。"""

    conversation_id: str = Field(min_length=1, max_length=36, description="前端生成的会话 UUID")
    query: str = Field(min_length=1, max_length=4000, description="用户问题")
    # 是否使用知识库检索。关闭时退化为纯对话（不检索、不引用）。
    knowledge_bool: bool = True
    # 以下为可选的单次覆盖项，为空时使用全局配置
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)


class CreateConversationRequest(BaseModel):
    """新建会话请求。`title` 可选，为空时由后端根据首条消息自动生成。"""

    title: str | None = Field(default=None, max_length=255)


class ConversationResponse(BaseModel):
    """会话信息。"""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表。遵守第 6.3 节的列表响应规范。"""

    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """一条消息。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    source_entries: list[SourceItem] | None
    trace_id: str | None
    created_at: datetime


class MessageListResponse(BaseModel):
    """会话的消息列表。"""

    items: list[MessageResponse]
    total: int
    conversation_id: str


class DeleteConversationResponse(BaseModel):
    """删除会话响应。"""

    status: str = "success"
    message: str
    conversation_id: str
