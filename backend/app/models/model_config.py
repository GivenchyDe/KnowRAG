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
        String(128), nullable=False, default="deepseek-v4-pro", server_default=text("'deepseek-v4-pro'")
    )
    llm_temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.1, server_default=text("0.1")
    )
    llm_max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2048, server_default=text("2048")
    )

    # --- Embedding ---
    # 本系统只支持远程 provider（本地模型方案已于 2026-10-02 移除），默认值因此是 qwen。
    embed_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="qwen", server_default=text("'qwen'")
    )
    embed_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 向量模型的接口地址。只有 provider = custom 时才被使用：
    #   - qwen 走 DashScope 向量端点，地址由 SDK 固定；
    #   - zhipu / siliconflow 的地址来自 provider 目录（default_base_url）；
    #   - custom 没有任何可用的默认地址，必须由用户填写，因此需要一列来存。
    # 可空：非 custom 的 provider 不需要这一列有值。
    embed_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embed_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="text-embedding-v4",
        server_default=text("'text-embedding-v4'"),
    )
    # 向量维度由后端按模型**实测**值维护（连接测试 / 摄取时写回），前端不提供输入框。
    # 默认值只是为了新建配置行时字段非空，第一次真正调用模型后会被校正。
    embed_dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024, server_default=text("1024")
    )

    # --- Reranker ---
    rerank_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="qwen", server_default=text("'qwen'")
    )
    rerank_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 同 embed_base_url：只有 provider = custom 时才被使用。
    rerank_base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rerank_model: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="gte-rerank-v2",
        server_default=text("'gte-rerank-v2'"),
    )

    def __repr__(self) -> str:
        """只输出非敏感字段：加密后的 Key 不进入日志或调试输出。"""
        return (
            f"<ModelConfig id={self.id} llm={self.llm_provider}/{self.llm_model} "
            f"embed={self.embed_provider}/{self.embed_model} "
            f"rerank={self.rerank_provider}/{self.rerank_model}>"
        )
