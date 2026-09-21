"""数据库会话管理。

提供 `SessionLocal` 工厂与 FastAPI 依赖 `get_db`。
Phase 1 采用同步 SQLAlchemy：用户注册/登录是低并发短事务，同步实现更简单可靠，
也便于 Alembic 复用同一套引擎配置。
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping 让连接在使用前先探活。MySQL 默认 8 小时断开空闲连接
# （wait_timeout），没有这个选项时，长时间无请求后第一个请求必定报
# "MySQL server has gone away"。
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个会话，请求结束后必定关闭。

    不在这里自动 commit：事务边界由 service 层显式控制，
    避免读接口因为依赖注入的隐式提交而产生意外写入。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
