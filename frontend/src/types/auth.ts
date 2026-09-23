/**
 * 认证相关类型。
 *
 * 字段与 `docs/DESIGN_IMPLEMENTATION.md` 第 6.1 节的 API 契约一一对应，
 * 后端 `backend/app/schemas/auth.py` 是唯一来源；接口变更时必须同步这里。
 */

/** 用户信息，对应 GET /auth/me 与 UserResponse */
export interface User {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
  /** 头像外链路径（如 `/api/media/avatars/xxx.png`）；未设置为 null */
  avatar_url: string | null;
  /** ISO 8601 字符串，后端按 UTC 输出 */
  created_at: string;
}

/** 修改资料请求，对应 PATCH /auth/me。只提交要改的字段。 */
export interface UpdateProfileRequest {
  username?: string;
  /** 传 null 表示清空邮箱；不传表示不修改 */
  email?: string | null;
}

/** 头像上传响应，对应 POST /auth/me/avatar */
export interface AvatarUploadResponse {
  avatar_url: string;
  message: string;
}

/** 注册请求，对应 POST /auth/register */
export interface RegisterRequest {
  username: string;
  password: string;
  email?: string | null;
}

/** 注册响应 */
export interface RegisterResponse {
  id: number;
  username: string;
}

/** 登录请求，对应 POST /auth/login */
export interface LoginRequest {
  username: string;
  password: string;
}

/** token 对，对应 POST /auth/login 与 POST /auth/refresh */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
