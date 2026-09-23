"""add is_pinned to conversations

Revision ID: d8f2b6a15c74
Revises: c4a7e10b93d5
Create Date: 2026-09-23 10:00:00.000000+00:00

新增 `conversations.is_pinned`，用于会话列表的「置顶」。

用布尔值而不是 `pinned_at` 时间戳：产品上只有「置顶 / 取消置顶」两个状态，
多个置顶项之间沿用 `updated_at` 排序即可，再引入时间维度会让排序规则更难解释。
排序见 `chat_service.list_conversations`：`is_pinned DESC, updated_at DESC`。

NOT NULL 且 server_default='0'：已有会话默认不置顶，无需回填。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2b6a15c74'
down_revision: str | None = 'c4a7e10b93d5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用本次迁移。"""
    op.add_column(
        'conversations',
        sa.Column(
            'is_pinned',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )


def downgrade() -> None:
    """回滚本次迁移。

    必须提供可用的回滚实现：留空会让 `alembic downgrade` 静默成功但结构未变，
    之后再 upgrade 会因列已存在而失败。
    """
    op.drop_column('conversations', 'is_pinned')
