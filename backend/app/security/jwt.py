"""JWT 的签发与校验。

算法固定为 HS256：本项目是单体部署，签发与校验是同一个进程，
无需 RS256 的非对称密钥管理成本。

安全边界（遵守 `docs/CODING_CONVENTIONS.md` 第 8.2 节）：
- token 本身不得写入日志。JWT 的 payload 只是 base64 编码，**任何人都能解开查看**，
  因此 payload 中只放用户 ID 与类型，绝不放密码、API Key 等敏感信息。

两种 token 的职责区分：
- access token：短期（默认 30 分钟），随每个请求发送，用于鉴权；
- refresh token：长期（默认 7 天），**只能**用于换取新的 access token，不能用于访问业务接口。
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.core.config import get_settings
from app.db.base import utc_now

# 写入 payload 的 "typ" 声明，用于防止把 refresh token 当作 access token 使用。
_JWT_ALGORITHM = "HS256"


class TokenType(StrEnum):
    """token 用途类型。"""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenError(Exception):
    """token 无效（签名错误、格式错误、类型不符）。"""


class TokenExpiredError(TokenError):
    """token 已过期。单独建模是为了让调用方可以返回不同的错误提示。"""


def _create_token(user_id: int, token_type: TokenType, expires_delta: timedelta) -> str:
    """签发一个 token。"""
    settings = get_settings()
    issued_at = utc_now()
    payload: dict[str, Any] = {
        # PyJWT 要求 sub 为字符串，这里显式转换，避免后续版本严格校验时报错。
        "sub": str(user_id),
        "typ": token_type.value,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    """签发 access token。"""
    settings = get_settings()
    return _create_token(
        user_id, TokenType.ACCESS, timedelta(minutes=settings.jwt_expire_minutes)
    )


def create_refresh_token(user_id: int) -> str:
    """签发 refresh token。"""
    settings = get_settings()
    return _create_token(
        user_id, TokenType.REFRESH, timedelta(days=settings.jwt_refresh_expire_days)
    )


def decode_token(token: str, expected_type: TokenType) -> int:
    """校验并解析 token，返回其中的 user_id。

    `expected_type` 必须显式传入：只校验签名不足以区分 access 与 refresh，
    否则一个长期有效的 refresh token 就能直接当 access token 使用，
    使「短期 access + 长期 refresh」的设计失去意义。
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("token 已过期") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("token 无效") from exc

    if payload.get("typ") != expected_type.value:
        raise TokenError("token 类型不匹配")

    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        raise TokenError("token 缺少有效的用户标识")
    return int(subject)
