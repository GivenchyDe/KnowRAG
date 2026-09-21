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
  /** ISO 8601 字符串，后端按 UTC 输出 */
  created_at: string;
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
