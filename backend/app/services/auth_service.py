"""认证业务逻辑。

分层约定（`docs/CODING_CONVENTIONS.md` 第 3.3 节）：router 只负责参数接收与依赖注入，
所有数据库读写、密码校验、token 签发都放在本模块。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.security.jwt import (
    TokenError,
    TokenExpiredError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.security.password import hash_password, verify_password_or_dummy


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """按主键查询用户。"""
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    """按用户名查询用户。

    这里使用普通的等值比较，不做 `lower()` 归一化：库的排序规则
    `utf8mb4_0900_ai_ci` 已经保证大小写不敏感匹配，
    应用层再转换一次反而会掩盖排序规则被意外改动的风险。
    """
    return db.scalar(select(User).where(User.username == username))


def get_user_by_email(db: Session, email: str) -> User | None:
    """按邮箱查询用户。大小写行为同上，依赖库级排序规则。"""
    return db.scalar(select(User).where(User.email == email))


def authenticate_user(db: Session, username: str, password: str) -> User:
    """校验用户名密码，成功返回用户对象。

    错误处理策略：
    - 「用户不存在」与「密码错误」返回**完全相同**的错误码与文案，
      避免攻击者通过响应差异枚举出系统中存在哪些用户名；
    - 同时用 `verify_password_or_dummy` 让两条路径都执行一次 bcrypt 校验，
      否则「用户不存在」只需几毫秒而「密码错误」需要约 200ms，
      这个耗时差异本身就能被远程测量出来，使统一文案失去意义；
    - 「账号已禁用」单独提示，因为它不是敏感信息，且用户需要明确原因才能求助。
    """
    user = get_user_by_username(db, username)
    password_ok = verify_password_or_dummy(password, user.hashed_password if user else None)

    if user is None or not password_ok:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户名或密码错误")

    if not user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")

    return user


def create_user(db: Session, username: str, password: str, email: str | None) -> User:
    """创建用户。

    唯一性检查放在插入前显式查询，而不是捕获数据库的 IntegrityError：
    这样能给出「哪一个字段重复」的明确提示，且不依赖具体驱动抛出的异常形态
    （pymysql 与 psycopg 的异常码并不一致，捕获型实现难以跨驱动复用）。
    """
    if get_user_by_username(db, username) is not None:
        raise AppError(ErrorCode.VALIDATION_ERROR, "该用户名已被注册")

    if email:
        if get_user_by_email(db, email) is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "该邮箱已被注册")

    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_tokens(user: User) -> TokenResponse:
    """为用户签发 access + refresh token。"""
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


def refresh_access_token(db: Session, refresh_token: str) -> TokenResponse:
    """用 refresh token 换取新的 token 对。

    这里同时轮换 refresh token（返回新的 refresh_token），而不是原样返回旧的：
    旧 token 在客户端被替换后会自然失效，缩小长期 token 泄漏后的可用窗口。
    """
    try:
        user_id = decode_token(refresh_token, TokenType.REFRESH)
    except TokenExpiredError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录") from exc
    except TokenError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "刷新凭据无效") from exc

    user = get_user_by_id(db, user_id)
    if user is None:
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不存在")
    if not user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")

    return issue_tokens(user)
