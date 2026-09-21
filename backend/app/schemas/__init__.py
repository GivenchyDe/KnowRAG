"""Schema 包：请求体与响应体定义（对外 API 契约）。"""

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserResponse,
)
from app.schemas.config import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ModelConfigResponse,
    ModelConfigUpdate,
    ModelConfigUpdateResponse,
    ProviderOptionResponse,
    ProvidersResponse,
)

__all__ = [
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "LoginRequest",
    "ModelConfigResponse",
    "ModelConfigUpdate",
    "ModelConfigUpdateResponse",
    "ProviderOptionResponse",
    "ProvidersResponse",
    "RefreshRequest",
    "RegisterRequest",
    "RegisterResponse",
    "TokenResponse",
    "UserResponse",
]
