"""用户模型。

对应 `docs/DESIGN_IMPLEMENTATION.md` 第 4.1 节 users 表。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """用户表。

    唯一约束说明：库使用 `utf8mb4_0900_ai_ci` 排序规则（大小写不敏感），
    因此 `username` 与 `email` 的唯一索引会把 `Alice` 与 `alice` 视为同一用户。
    这是防止仿冒账号的主动设计，依赖库级排序规则而非应用层 `lower()` 转换，
    所以**不要在应用层再做一次 lower 归一化**，否则会掩盖排序规则被改动的风险。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 头像的**外链路径**（如 `/media/avatars/<随机名>.png`），不是磁盘路径。
    #
    # 只存路径而不存图片本身：用户表会被频繁读取（每次 /auth/me、每次鉴权 inject），
    # 把二进制塞进这一行会让所有查询都背上无关的负载。
    # 文件名用随机 UUID（见 auth_service.save_avatar），因此该 URL 不可枚举——
    # 否则任何人按 user_id 递增就能把全站头像拉一遍。
    avatar_url: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:
        """只输出非敏感字段，避免密码哈希进入日志或调试输出。"""
        return f"<User id={self.id} username={self.username!r} is_active={self.is_active}>"
