"""Schema 包：请求体与响应体定义（对外 API 契约）。"""

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
)

__all__ = [
    "LoginRequest",
    "RefreshRequest",
    "RegisterRequest",
    "RegisterResponse",
    "TokenResponse",
    "UserResponse",
]
