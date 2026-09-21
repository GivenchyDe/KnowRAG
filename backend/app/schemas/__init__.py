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
from app.schemas.documents import (
    DeleteDocumentResponse,
    DocumentListResponse,
    DocumentResponse,
    IndexStatusResponse,
    RebuildResponse,
    TaskResponse,
    UploadResponse,
)

__all__ = [
    "ConnectionTestRequest",
    "ConnectionTestResponse",
    "DeleteDocumentResponse",
    "DocumentListResponse",
    "DocumentResponse",
    "IndexStatusResponse",
    "LoginRequest",
    "ModelConfigResponse",
    "ModelConfigUpdate",
    "ModelConfigUpdateResponse",
    "ProviderOptionResponse",
    "ProvidersResponse",
    "RebuildResponse",
    "RefreshRequest",
    "RegisterRequest",
    "RegisterResponse",
    "TaskResponse",
    "TokenResponse",
    "UploadResponse",
    "UserResponse",
]
