"""消息模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.7 节 messages 表。

`source_entries` 用 JSON 存放引用来源。MySQL 8.0 支持原生 JSON 类型，
但本项目的这个字段只做整体读写、不建 JSON 索引，因此无功能缺失。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class MessageRole(StrEnum):
    """消息角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(Base, TimestampMixin):
    """一条消息。

    注意时间字段来自 `TimestampMixin`（created_at / updated_at），
    没有额外的单独时间列：消息一旦写入就不会被修改，
    `created_at` 已足够用于排序与展示。
    """

    __tablename__ = "messages"
    __table_args__ = (
        # 按会话取历史消息是最频繁的操作，且需要按时间排序。
        Index("ix_messages_user_conv_created", "user_id", "conversation_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # 这里存前端的 conversation_id（UUID），而不是 conversations 表的主键：
    # 记忆键与检索都基于 "user_id:conversation_id"，直接用 UUID 可以少一次关联查询。
    # 不设外键约束是因为会话与消息都可能被独立清理（删除会话时批量删消息），
    # 加外键会让删除顺序变得脆弱。
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 引用来源列表，结构见 schemas/chat.py 的 SourceItem
    source_entries: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<Message user_id={self.user_id} role={self.role} len={len(self.content)}>"
