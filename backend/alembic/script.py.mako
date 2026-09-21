"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """应用本次迁移。"""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """回滚本次迁移。

    必须提供可用的回滚实现而不是留空：留空会让 `alembic downgrade` 静默成功
    但数据库结构实际未变，之后再次 upgrade 会因对象已存在而失败。
    """
    ${downgrades if downgrades else "pass"}
