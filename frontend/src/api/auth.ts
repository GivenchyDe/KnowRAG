import { fetchWithAuth, request } from "@/api/client";
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
 * 路径带 `/auth` 前缀，而 `API_BASE_URL` 默认是 `/api`，因此必须用
 * `absolutePath: true` 绕过前缀——否则会请求到不存在的 `/api/auth/login`。
 *
 * 这些接口自身不需要 Authorization 头（登录前没有 token，刷新用的是 refresh token），
 * 因此统一带 `skipAuth: true`。认证头的注入与过期处理由 `api/client.ts` 统一负责，
 * 各 api 模块不再手工拼 `Authorization`。
 */

export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  return request<RegisterResponse>("/auth/register", {
    method: "POST",
    json: payload,
    absolutePath: true,
    skipAuth: true,
  });
}

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    json: payload,
    absolutePath: true,
    skipAuth: true,
  });
}

export async function refresh(refreshToken: string): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/refresh", {
    method: "POST",
    json: { refresh_token: refreshToken },
    absolutePath: true,
    skipAuth: true,
  });
}

export async function fetchCurrentUser(): Promise<User> {
  // token 由 client 自动附加，这里不再需要传入。
  return request<User>("/auth/me", { absolutePath: true });
}

/** 供需要自行处理响应流的调用方使用（目前只有 SSE 用到）。 */
export { fetchWithAuth };
