"""认证路由。

路径规范（`docs/CODING_CONVENTIONS.md` 第 6.1 节）：认证接口统一挂在 `/auth/...`。
本模块只做「收参数 → 调 service → 返回 schema」，不含任何业务判断。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AvatarUploadResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.security.dependencies import get_current_active_user, get_current_user
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


@router.patch("/me", response_model=UserResponse, summary="修改当前用户资料")
def update_current_user(
    payload: UpdateProfileRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> User:
    """修改用户名 / 邮箱。

    用 `model_fields_set` 而不是 `payload.username is not None` 来判断「哪些字段要改」：
    两者在语义上不同——`{"email": null}` 是「清空邮箱」，而请求体里不出现 `email`
    则是「不动邮箱」。只看 `is not None` 会把这两种情况混为一谈。
    """
    changes: dict[str, object] = {}
    if "username" in payload.model_fields_set:
        changes["username"] = payload.username
    if "email" in payload.model_fields_set:
        changes["email"] = payload.email

    if not changes:
        raise AppError(ErrorCode.VALIDATION_ERROR, "请求体里没有需要更新的字段")

    return auth_service.update_profile(db, current_user, changes)


@router.post("/me/avatar", response_model=AvatarUploadResponse, summary="上传头像")
async def upload_current_user_avatar(
    file: UploadFile = File(..., description="JPG / PNG / WebP，最大 2MB"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> AvatarUploadResponse:
    """上传并替换当前用户的头像。

    读文件时按「上限 + 1」字节读取，而不是 `await file.read()` 全量读取：
    后者会把一个 500MB 的请求体整个读进内存才轮到大小校验，等于自己制造了一个
    DoS 入口。多读 1 字节是为了能区分「刚好等于上限」与「超过上限」。

    真实的大小与格式校验都在 `auth_service.save_avatar` 里（含文件头魔数比对），
    这里只负责把字节取出来。
    """
    settings = get_settings()
    data = await file.read(settings.max_avatar_bytes + 1)
    user = auth_service.save_avatar(
        db,
        current_user,
        data=data,
        content_type=file.content_type,
        filename=file.filename,
    )
    return AvatarUploadResponse(avatar_url=user.avatar_url or "")
