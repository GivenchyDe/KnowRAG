import { request } from "@/api/client";
import type {
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
  User,
} from "@/types/auth";

/**
 * 认证接口。
 *
 * 路径带 `/auth` 前缀，`API_BASE_URL` 默认是 `/api`，因此这里必须用
 * `absolutePath: true` 绕过前缀——否则会请求到不存在的 `/api/auth/login`。
 * 开发环境由 Vite 代理 `/auth` 到后端，生产环境由 Nginx 反代。
 */

export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  return request<RegisterResponse>("/auth/register", {
    method: "POST",
    json: payload,
    absolutePath: true,
  });
}

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    json: payload,
    absolutePath: true,
  });
}

export async function refresh(refreshToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", {
    method: "POST",
    json: { refresh_token: refreshToken },
    absolutePath: true,
  });
}

export async function fetchCurrentUser(token: string): Promise<User> {
  return request<User>("/auth/me", {
    absolutePath: true,
    headers: { Authorization: `Bearer ${token}` },
  });
}
