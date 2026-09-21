"""安全能力：密码哈希与 JWT。

各模块均从具体子模块导入（如 `from app.security.jwt import ...`），
这里只做统一出口，避免调用方记忆文件位置。
"""

from app.security.jwt import (
    TokenError,
    TokenExpiredError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.security.password import (
    MAX_PASSWORD_BYTES,
    hash_password,
    verify_password,
    verify_password_or_dummy,
)

__all__ = [
    "MAX_PASSWORD_BYTES",
    "TokenError",
    "TokenExpiredError",
    "TokenType",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
    "verify_password_or_dummy",
]
