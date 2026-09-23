"""认证相关请求体与响应体。

字段校验放在 schema 层，便于在进入 service 之前就拒绝非法输入，
并按统一错误契约返回 422 VALIDATION_ERROR。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security.password import MAX_PASSWORD_BYTES

# 密码最小长度。设计文档未规定，这里取 8 位作为最低要求；
# 上限按 bcrypt 的 72 字节限制换算，中文字符占 3 字节，因此不能简单按字符数设 72。
_MIN_PASSWORD_LENGTH = 8


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(min_length=3, max_length=64, description="用户名")
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128, description="密码")
    email: EmailStr | None = Field(default=None, description="邮箱，可选")

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        """只允许字母、数字、下划线、连字符。

        限制字符集是为了避免用户名里混入空格或不可见字符导致登录时难以输入，
        也防止与将来的 URL 路由、@提及等特性冲突。
        """
        if not all(char.isalnum() or char in "_-" for char in value):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password_bytes(cls, value: str) -> str:
        """校验密码的 UTF-8 字节长度不超过 bcrypt 上限。

        必须按字节而非字符判断：一个中文汉字占 3 字节，
        单纯限制字符数会让 30 个汉字的密码超过 72 字节而被 bcrypt 静默截断。
        """
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(f"密码过长，UTF-8 编码后不能超过 {MAX_PASSWORD_BYTES} 字节")
        return value


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(min_length=1, max_length=64, description="用户名")
    password: str = Field(min_length=1, max_length=128, description="密码")


class RefreshRequest(BaseModel):
    """刷新 token 请求。"""

    refresh_token: str = Field(min_length=1, description="refresh token")


class UserResponse(BaseModel):
    """对外返回的用户信息。

    使用 `from_attributes` 直接从 ORM 对象构造，且**不包含** `hashed_password`，
    从类型层面保证密码哈希不会随响应泄漏。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    is_active: bool
    # 头像外链路径，未设置时为 null（前端退回文字头像）
    avatar_url: str | None = None
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    """修改个人资料。

    两个字段都是**可选**：前端只提交被改动的字段，未提交的字段保持原值。
    这一点不只是省流量——见 `username` 的校验说明。
    """

    username: str | None = Field(default=None, min_length=2, max_length=20, description="新用户名")
    email: EmailStr | None = Field(default=None, description="新邮箱")

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str | None) -> str | None:
        """字符集与注册保持一致；长度按产品要求收紧到 2-20。

        注意这里与 `RegisterRequest` 的 3-64 并不一致，是**有意的**：
        个人设置里的用户名是展示名，短一些更可读。
        由此带来一个边界情况——注册时用了 21 个字符以上的老用户，如果只改邮箱
        却把用户名一起提交，会被这里拒掉。因此前端**只提交真正改动过的字段**，
        老的超长用户名不会被重新校验。
        """
        if value is None:
            return None
        if not all(char.isalnum() or char in "_-" for char in value):
            raise ValueError("用户名只能包含字母、数字、下划线和连字符")
        return value


class AvatarUploadResponse(BaseModel):
    """头像上传结果。"""

    avatar_url: str
    message: str = "头像已更新"


class RegisterResponse(BaseModel):
    """注册响应，遵守 `docs/DESIGN_IMPLEMENTATION.md` 第 6.1 节的契约。"""

    id: int
    username: str


class TokenResponse(BaseModel):
    """登录与刷新 token 的响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - 这是 OAuth2 协议固定值，不是密钥
