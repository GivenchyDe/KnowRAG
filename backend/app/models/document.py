"""文档模型与状态枚举。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.3 节 documents 表。
`DocumentStatus` 同时被 ORM 与 API schema 引用，因此放在模型层作为唯一定义处。
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DocumentStatus(StrEnum):
    """文档生命周期状态。"""

    UPLOADED = "uploaded"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class Document(Base, TimestampMixin):
    """用户上传的原始文档。

    与 `ingestion_tasks` 的关系：一次上传产生一条 Document 与一条 IngestionTask；
    重建索引会为同一 Document 再产生新的 Task，因此是一对多。
    """

    __tablename__ = "documents"
    __table_args__ = (
        # 文档列表与删除都按用户过滤，加联合索引避免全表扫描。
        Index("ix_documents_user_status", "user_id", "status"),
        # sha256 用于同用户内的内容去重（同一份文件重复上传直接拒绝）。
        Index("ix_documents_user_sha256", "user_id", "sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentStatus.UPLOADED, server_default="uploaded"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} user_id={self.user_id} filename={self.filename!r} status={self.status}>"
