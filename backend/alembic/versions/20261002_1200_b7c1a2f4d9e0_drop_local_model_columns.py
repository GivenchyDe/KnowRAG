"""drop local model columns and switch provider defaults to qwen

本地模型方案已整体移除（见 `docs/DESIGN_IMPLEMENTATION.md` Phase 2 的移除说明），因此：

1. `model_configs.embed_model_path` / `rerank_model_path` 两列不再有任何消费者：
   本地模型加载已删除，索引指纹也不再包含路径，留着只会让人以为它能影响加载。
2. `embed_provider` / `rerank_provider` 的数据库默认值从 `'local'` 改为 `'qwen'`，
   `embed_model` / `rerank_model` 的默认值同步改为对应的远程模型名。
   不改的话，任何绕过 ORM 的插入都会造出一行"provider=qwen 但模型是 bge-m3"的矛盾配置。
3. 已存在的 `local` 行就地改写为远程取值：代码里已经没有任何 local 分支，
   留着这样的行会让检索/摄取直接报"不支持的 provider"。改写后这些行的 API Key
   需要使用者重新填写（它们原本也不需要 Key）。

Revision ID: b7c1a2f4d9e0
Revises: d8f2b6a15c74
Create Date: 2026-10-02 12:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1a2f4d9e0'
down_revision: str | None = 'd8f2b6a15c74'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用本次迁移。"""
    # 1) 先改数据，再改默认值：顺序反过来的话，中间态里任何一次插入都可能再产出一行 local。
    op.execute(
        "UPDATE model_configs SET embed_provider='qwen', embed_model='text-embedding-v4' "
        "WHERE embed_provider='local'"
    )
    op.execute(
        "UPDATE model_configs SET rerank_provider='qwen', rerank_model='gte-rerank-v2' "
        "WHERE rerank_provider='local'"
    )
    # 本地 LLM 走的是用户自填的 base_url（Ollama / vLLM 地址）。改到 DeepSeek 时必须清空，
    # 否则会拿着 http://localhost:11434/v1 去请求 DeepSeek —— 网络层就错了。
    op.execute(
        "UPDATE model_configs SET llm_provider='deepseek', llm_model='deepseek-chat', "
        "llm_base_url=NULL WHERE llm_provider='local'"
    )

    # 2) 默认值：provider 由 local 改为 qwen，模型名同步改为远程模型名。
    op.alter_column(
        "model_configs",
        "embed_provider",
        existing_type=sa.String(length=32),
        server_default=sa.text("'qwen'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "embed_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'text-embedding-v4'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "rerank_provider",
        existing_type=sa.String(length=32),
        server_default=sa.text("'qwen'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "rerank_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'gte-rerank-v2'"),
        existing_nullable=False,
    )

    # 3) 删除两列本地模型路径。先删 rerank 再删 embed，顺序无实际差别，只为可读。
    op.drop_column("model_configs", "rerank_model_path")
    op.drop_column("model_configs", "embed_model_path")


def downgrade() -> None:
    """回滚本次迁移。

    两列可以恢复（原本都是可空 Text），默认值也能改回 `local`；
    但**数据行无法回滚**：upgrade 把 local 行改写成了远程取值，
    而"哪几行原本是 local"这一信息在改写后不复存在。回滚后这些行会停留在远程取值上，
    需要按实际部署情况人工重填。
    """
    op.add_column("model_configs", sa.Column("embed_model_path", sa.Text(), nullable=True))
    op.add_column("model_configs", sa.Column("rerank_model_path", sa.Text(), nullable=True))

    op.alter_column(
        "model_configs",
        "embed_provider",
        existing_type=sa.String(length=32),
        server_default=sa.text("'local'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "embed_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'BAAI/bge-m3'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "rerank_provider",
        existing_type=sa.String(length=32),
        server_default=sa.text("'local'"),
        existing_nullable=False,
    )
    op.alter_column(
        "model_configs",
        "rerank_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'bge-reranker-large'"),
        existing_nullable=False,
    )
