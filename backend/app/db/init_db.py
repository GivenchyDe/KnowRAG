"""建表辅助脚本。

用途说明：本项目的数据库结构变更**统一走 Alembic 迁移**
（`docs/CODING_CONVENTIONS.md` 第 7.3 节），本模块不参与日常开发流程。
保留它只为一件事：在自动化测试里用 SQLite 内存库快速准备表结构，
避免测试必须先跑一遍 Alembic。

用法：
    python -m app.db.init_db          # 直接对当前 DATABASE_URL 建表（仅限本地调试）
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import engine

# 必须在建表前导入 models 包，否则 Base.metadata 中没有表定义。
import app.models  # noqa: F401  # isort: skip

logger = get_logger(__name__)


def create_all() -> None:
    """按当前 ORM 定义创建所有不存在的表。

    注意：这是「只增不改」的操作，不会修改已存在表的结构。
    真实的字段变更必须通过 Alembic 迁移完成。
    """
    Base.metadata.create_all(bind=engine)
    logger.info("已按 ORM 定义创建缺失的表：%s", ", ".join(sorted(Base.metadata.tables)))


if __name__ == "__main__":
    create_all()
