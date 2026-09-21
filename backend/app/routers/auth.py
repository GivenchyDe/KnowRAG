"""认证路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：认证接口统一挂在 `/auth/...`。
本模块只做「收参数 → 调 service → 返回 schema」，不含任何业务判断。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
)
from app.security.dependencies import get_current_user
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="注册用户",
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    """注册新用户。注册成功后不自动登录，由前端跳转登录页。"""
    user = auth_service.create_user(
        db,
        username=payload.username,
        password=payload.password,
        email=payload.email,
    )
    return RegisterResponse(id=user.id, username=user.username)


@router.post("/login", response_model=TokenResponse, summary="登录并获取 token")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """校验用户名密码并签发 token 对。"""
    user = auth_service.authenticate_user(db, payload.username, payload.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse, summary="刷新 token")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """用 refresh token 换取新的 token 对。"""
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.get("/me", response_model=UserResponse, summary="获取当前用户")
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """返回当前登录用户信息。

    这里依赖 `get_current_user` 而不是 `get_current_active_user`：
    被禁用的用户也应当能看到自己的账号状态，否则前端无法给出「账号已被禁用」的提示。
    """
    return current_user
