"""会话模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.6 节 conversations 表。

`conversation_id` 由前端生成 UUID，与 `user_id` 共同构成唯一约束。
后端使用的会话记忆键是 `f"{user_id}:{conversation_id}"`：
同一用户开两个标签页时各自拥有独立会话，不会共享上下文。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Conversation(Base, TimestampMixin):
    """一次会话。"""

    __tablename__ = "conversations"
    __table_args__ = (
        # 同一用户下 conversation_id 唯一。不同用户可以使用相同的 UUID 前缀也不会冲突，
        # 但查询时永远带上 user_id，因此不会互相可见。
        Index("ix_conversations_user_conv", "user_id", "conversation_id", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="新会话", server_default="新会话"
    )
    # 置顶。列表排序为「置顶优先，其次按更新时间」。
    #
    # 用布尔值而不是 pinned_at 时间戳：产品上只需要「置顶 / 取消置顶」两个状态，
    # 多个置顶项之间沿用 updated_at 排序就够，再引入一个时间维度只会让排序规则更难解释。
    is_pinned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    def __repr__(self) -> str:
        return f"<Conversation user_id={self.user_id} conversation_id={self.conversation_id} title={self.title!r}>"
