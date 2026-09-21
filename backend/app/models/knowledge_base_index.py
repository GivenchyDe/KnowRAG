"""知识库索引版本模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.5 节 knowledge_base_indexes 表。

为什么需要这张表：Embedding 模型一旦变化，旧向量与新向量不在同一语义空间，
混用会导致检索质量下降甚至维度不匹配而查询失败。因此每个用户的知识库有
明确的「版本」，版本号也体现在 Chroma 集合名里（`user_{id}_kb_v{n}`），
重建时写入新集合、成功后再切换，旧集合随后删除。
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class IndexStatus(StrEnum):
    """索引状态。

    - `building`：正在构建，不可用于检索；
    - `ready`：可用于检索；
    - `stale`：Embedding 配置已变更，向量空间不再匹配，需重建；
    - `failed`：构建失败，需重建。
    """

    BUILDING = "building"
    READY = "ready"
    STALE = "stale"
    FAILED = "failed"


class KnowledgeBaseIndex(Base, TimestampMixin):
    """用户知识库索引的一条版本记录。"""

    __tablename__ = "knowledge_base_indexes"
    __table_args__ = (
        # 按用户查询「当前可用索引」是最频繁的操作。
        Index("ix_kb_indexes_user_status", "user_id", "status"),
        # 集合名在 Chroma 中必须唯一，这里也约束住，避免并发重建产生同名集合。
        Index("ix_kb_indexes_collection", "collection_name", unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    # 构建该索引时「会影响向量空间」的全部参数指纹（provider|model|dimension|path）。
    # 必须存指纹而不是逐列比较：本地模型路径（embed_model_path）没有独立列，
    # 而它变化时向量空间同样改变——只比较 provider/model 会漏判，
    # 导致换了本地模型目录后旧索引仍被当作可用，静默返回错误检索结果。
    embedding_signature: Mapped[str] = mapped_column(String(512), nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False)
    index_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=IndexStatus.BUILDING, server_default="building"
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeBaseIndex user_id={self.user_id} collection={self.collection_name} "
            f"v={self.index_version} status={self.status}>"
        )
