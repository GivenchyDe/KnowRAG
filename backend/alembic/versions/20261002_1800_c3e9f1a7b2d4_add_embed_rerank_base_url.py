"""add embed/rerank base_url columns and retire the deepseek-chat default

两件事，都是为了 `custom` provider 与新的预设模型方案能真正落地：

1. **新增 `embed_base_url` / `rerank_base_url`（可空）**。
   在此之前只有 LLM 有 `llm_base_url`：向量与重排的端点要么由 SDK 固定
   （qwen），要么由代码常量固定，因此没有可存的地址。现在要支持
   `provider = custom`（用户自带的 OpenAI 兼容端点），必须有一列存用户填的地址；
   没有这一列就没法保存，只能做成"界面上能选、一保存就报错"的半成品。
   两列都可空，非 custom 的 provider 保持 NULL，旧数据不受影响。

2. **`llm_model` 的默认值由 `'deepseek-chat'` 改为 `'deepseek-v4-pro'`，
   并把库里残留的旧模型名就地改写**。
   `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 下线（官方向 v4 迁移公告），
   继续带着这两个名字调用会直接失败；而它们正是本表此前两版的默认值，
   因此既有的配置行极可能还停在这两个名字上——不改写的话，问答会因为
   一个"早就该换掉的名字"而报模型不存在。

Revision ID: c3e9f1a7b2d4
Revises: b7c1a2f4d9e0
Create Date: 2026-10-02 18:00:00.000000+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e9f1a7b2d4'
down_revision: str | None = 'b7c1a2f4d9e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 已下线的旧模型名。集中在这里，便于日后新增退役名时一处修改。
_RETIRED_DEEPSEEK_MODELS: tuple[str, ...] = ("deepseek-chat", "deepseek-reasoner")


def upgrade() -> None:
    """应用本次迁移。"""
    # 1) 两个可空地址列。先加列再改数据：MySQL 的 DDL 隐式提交，
    #    把"加列"放在前面可以让中途失败时的状态更容易理解（列在、数据未改）。
    op.add_column(
        "model_configs", sa.Column("embed_base_url", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "model_configs", sa.Column("rerank_base_url", sa.String(length=255), nullable=True)
    )

    # 2) 先改数据，再改默认值：顺序反过来的话，中间态里任何一次插入都可能
    #    再产出一行带退役模型名的配置。
    retired = ", ".join(f"'{name}'" for name in _RETIRED_DEEPSEEK_MODELS)
    op.execute(
        "UPDATE model_configs SET llm_model='deepseek-v4-pro' "
        f"WHERE llm_provider='deepseek' AND llm_model IN ({retired})"
    )

    op.alter_column(
        "model_configs",
        "llm_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'deepseek-v4-pro'"),
        existing_nullable=False,
    )


def downgrade() -> None:
    """回滚本次迁移。

    两个地址列可以删掉；`llm_model` 的默认值也能改回 `'deepseek-chat'`，
    但**数据行不再回滚**：upgrade 把退役的模型名改写成了 `deepseek-v4-pro`，
    而"哪几行原本是 deepseek-chat 还是 deepseek-reasoner"已经无从区分。
    何况回滚那些行等于把配置重新指回一个已下线的模型，只会让问答失败——
    需要旧名称时应当由使用者按实际账号可用模型显式填写。
    """
    op.alter_column(
        "model_configs",
        "llm_model",
        existing_type=sa.String(length=128),
        server_default=sa.text("'deepseek-chat'"),
        existing_nullable=False,
    )

    op.drop_column("model_configs", "rerank_base_url")
    op.drop_column("model_configs", "embed_base_url")
