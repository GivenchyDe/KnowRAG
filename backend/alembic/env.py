"""Alembic 迁移环境。

关键约定：
1. **连接串不在 alembic.ini 里写死**，而是从 `app.core.config` 读取，
   与后端运行时共用同一份配置，避免「迁移连 A 库、服务连 B 库」这类事故；
2. `target_metadata` 指向 `Base.metadata`，并显式导入 `app.models`，
   否则 autogenerate 会认为所有表都该被删除；
3. `compare_type=True` 让字段类型变更也能被 autogenerate 检测到，
   否则改类型必须手写迁移。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base

# 导入所有模型，确保 Base.metadata 中已注册全部表定义。
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用应用配置覆盖 alembic.ini 中的占位连接串。
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 文件，不连接数据库。

    用于「先审阅 SQL 再上生产」的场景，命令形如：
        alembic upgrade head --sql > migration.sql
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并直接执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
