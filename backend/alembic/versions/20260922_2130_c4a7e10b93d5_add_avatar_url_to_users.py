"""add avatar_url to users

Revision ID: c4a7e10b93d5
Revises: 22a19e3642c9
Create Date: 2026-09-22 21:30:00.000000+00:00

新增 `users.avatar_url`：存放头像的**外链路径**（`/media/avatars/<随机名>.<ext>`），
而不是图片本身。头像文件落在磁盘上，由 `main.py` 的 StaticFiles 挂载对外提供。

选 nullable 且无 server_default：已有用户的头像为空是合法状态
（前端会退回用用户名首字母生成的文字头像），不需要回填。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4a7e10b93d5'
down_revision: str | None = '22a19e3642c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """应用本次迁移。"""
    op.add_column('users', sa.Column('avatar_url', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """回滚本次迁移。

    必须提供可用的回滚实现：留空会让 `alembic downgrade` 静默成功但结构未变，
    之后再 upgrade 会因列已存在而失败。
    注意回滚只删列，不删磁盘上的头像文件——那是数据清理，不属于 schema 迁移的职责。
    """
    op.drop_column('users', 'avatar_url')
