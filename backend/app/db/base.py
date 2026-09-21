"""数据库基础工具。

本模块只提供三类东西：
1. `Base`：所有 ORM 模型的声明式基类；
2. `utc_now`：全项目统一的时间来源；
3. `TimestampMixin`：`created_at` / `updated_at` 的公共实现。

时间约定（遵守 `docs/DESIGN_IMPLEMENTATION.md` 第 4.0 节）：
MySQL 的 `DATETIME` 不保存时区，因此**全项目统一写入 UTC 的 naive datetime**，
不使用 `datetime.now()`（本地时间）也不使用带 tzinfo 的对象——否则同一列里会混入两种
时间基准，跨时区读取时出现错乱。API 响应层再统一按 ISO 8601 加 `Z` 后缀输出。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 ORM 模型的声明式基类。

    Alembic autogenerate 依赖 `Base.metadata`，因此所有模型模块都必须被导入一次，
    确保表定义已注册到 metadata（见 `app/models/__init__.py`）。
    """


def utc_now() -> datetime:
    """返回当前 UTC 时间，去掉 tzinfo 以便存入 MySQL 的 DATETIME 列。

    用 `datetime.now(UTC)` 而非 `utcnow()`：后者在 Python 3.12 起已弃用。
    """
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    """为模型提供 `created_at` / `updated_at` 两个通用字段。

    - 插入时由 Python 侧写入 UTC 时间，避免依赖数据库所在服务器的时区设置；
    - 更新时同时使用 `onupdate`，保证任何 ORM 更新都会自动刷新 `updated_at`。

    数据库侧默认值必须写成 MySQL 的 `CURRENT_TIMESTAMP`。若写成 `func.now()`，
    SQLAlchemy 会渲染为 `now()`，而 **MySQL 没有 `now()` 函数**，建表会直接失败
    （PostgreSQL 才有）。用 `text("CURRENT_TIMESTAMP")` 明确表达方言无关的意图。

    注意这里没有使用 `ON UPDATE CURRENT_TIMESTAMP`：时间戳由应用层统一写入 UTC，
    交给数据库自动更新会引入「数据库服务器本地时间」这一不确定因素。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utc_now, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
