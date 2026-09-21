"""FastAPI 依赖注入。

Phase 1 只提供「取当前登录用户」。所有受保护接口必须通过 `get_current_user`
拿到用户，**绝不允许**从请求体或查询参数读取 `user_id`
（`docs/CODING_CONVENTIONS.md` 第 3.3 节明令禁止）。
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models.user import User
from app.security.jwt import TokenError, TokenExpiredError, TokenType, decode_token
from app.services.auth_service import get_user_by_id


def _extract_bearer_token(request: Request) -> str:
    """从 Authorization 头中取出 Bearer token。

    不使用 FastAPI 的 `OAuth2PasswordBearer`：那套依赖默认指向
    `/auth/token` 表单登录端点，与本项目「JSON 登录 + JWT」的契约不符，
    且它会在未认证时返回 401 之外的响应格式，无法套用统一错误契约。
    """
    header = request.headers.get("Authorization")
    if not header:
        raise AppError(ErrorCode.UNAUTHORIZED, "缺少认证信息，请先登录")

    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AppError(ErrorCode.UNAUTHORIZED, "认证头格式应为 `Bearer <token>`")

    return token.strip()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """解析 token 并返回当前用户。"""
    token = _extract_bearer_token(request)
    try:
        user_id = decode_token(token, TokenType.ACCESS)
    except TokenExpiredError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "登录已过期，请重新登录") from exc
    except TokenError as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, "认证凭据无效，请重新登录") from exc

    user = get_user_by_id(db, user_id)
    if user is None:
        # token 签名有效但用户已被删除：属于凭据失效，而不是资源不存在。
        raise AppError(ErrorCode.UNAUTHORIZED, "用户不存在，请重新登录")

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """在 `get_current_user` 基础上额外要求账号处于启用状态。

    业务接口一律依赖本函数；只有「查询自己的信息」这类接口可以放宽，
    以便被禁用的用户看到自己的状态。
    """
    if not current_user.is_active:
        raise AppError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")
    return current_user
