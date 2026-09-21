"""文档摄取任务模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.4 节 ingestion_tasks 表。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class IngestionStatus(StrEnum):
    """摄取任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class IngestionTask(Base, TimestampMixin):
    """文档摄取任务。

    任务与文档是多对一：重建索引会为同一文档创建新的任务记录，
    这样「历史失败原因」不会被新任务覆盖掉。
    """

    __tablename__ = "ingestion_tasks"
    __table_args__ = (
        # 前端按 task_id 轮询状态，必须唯一且带索引。
        Index("ix_ingestion_tasks_task_id", "task_id", unique=True),
        Index("ix_ingestion_tasks_user_status", "user_id", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IngestionStatus.PENDING, server_default="pending"
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<IngestionTask task_id={self.task_id} document_id={self.document_id} "
            f"status={self.status} progress={self.progress}>"
        )
