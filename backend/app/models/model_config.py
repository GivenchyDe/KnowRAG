"""全局模型配置模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.2 节 model_configs 表。

设计要点：本表**只保存全局唯一一行**。模型 API Key 由用户在设置页自行填写，
不按用户隔离，因此没有「每个用户一条」的记录。`user_id` 仅记录最近一次修改者，
便于审计「谁改过全局模型配置」。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ModelConfig(Base, TimestampMixin):
    """全局模型配置（单行）。

    非空字段同时声明 `default` 与 `server_default`：
    - `default` 是 SQLAlchemy 在 ORM 插入时填的值；
    - `server_default` 是数据库层的默认值约束。
    只写前者的话，字段在数据库里没有默认值，任何绕过 ORM 的插入
    （例如手工 SQL、将来用原生 SQL 批量初始化）都会因 NOT NULL 而失败。
    """

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 可空：首次由系统创建默认配置时还没有任何用户修改过，此时记录为 NULL。
    # ondelete="SET NULL"：用户被删除时配置行必须保留，否则系统会失去全局模型配置。
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # --- LLM ---
    llm_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="deepseek", server_default=text("'deepseek'")
    )
    # 加密后的 API Key。用 Text 而不是 VARCHAR：Fernet 密文比明文长约 2 倍，
    # VARCHAR 超长在 MySQL 严格模式下会直接报错，Text 没有长度陷阱。
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    llm_model: Mapped[str] = mapped_column(
        String(128), nullable=False, default="deepseek-chat", server_default=text("'deepseek-chat'")
    )
    llm_temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.1, server_default=text("0.1")
    )
    llm_max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2048, server_default=text("2048")
    )

    # --- Embedding ---
    embed_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local", server_default=text("'local'")
    )
    embed_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    embed_model: Mapped[str] = mapped_column(
        String(128), nullable=False, default="BAAI/bge-m3", server_default=text("'BAAI/bge-m3'")
    )
    embed_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    embed_dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024, server_default=text("1024")
    )

    # --- Reranker ---
    rerank_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="local", server_default=text("'local'")
    )
    rerank_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    rerank_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="bge-reranker-large",
        server_default=text("'bge-reranker-large'"),
    )
    rerank_model_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        """只输出非敏感字段：加密后的 Key 不进入日志或调试输出。"""
        return (
            f"<ModelConfig id={self.id} llm={self.llm_provider}/{self.llm_model} "
            f"embed={self.embed_provider}/{self.embed_model} "
            f"rerank={self.rerank_provider}/{self.rerank_model}>"
        )
