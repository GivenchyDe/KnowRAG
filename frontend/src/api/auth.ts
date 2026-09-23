import { fetchWithAuth, request } from "@/api/client";
import type {
  AvatarUploadResponse,
  LoginRequest,
  RegisterRequest,
  RegisterResponse,
  TokenResponse,
  UpdateProfileRequest,
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

/**
 * 修改当前用户资料。
 *
 * 只提交发生变化、或用户明确清空的字段：后端按「请求体里出现了哪些键」来判断
 * 要更新什么，把未改动的字段一并提交会让它被重新校验一遍
 * （例如注册时用了 21 个字符以上的老用户名，会在只改邮箱时被判为超长）。
 */
export async function updateProfile(payload: UpdateProfileRequest): Promise<User> {
  return request<User>("/auth/me", {
    method: "PATCH",
    json: payload,
    absolutePath: true,
  });
}

/**
 * 上传头像。
 *
 * 用 `form` 而不是 `json`：`api/client.ts` 在该分支下不手动设置 Content-Type，
 * 交给浏览器补 multipart 边界——手写会漏掉 boundary 导致后端解析失败。
 */
export async function uploadAvatar(file: File): Promise<AvatarUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<AvatarUploadResponse>("/auth/me/avatar", {
    method: "POST",
    form,
    absolutePath: true,
    // 头像是本地已有文件，上传很快；给 60s 已经足够覆盖慢速网络
    timeoutMs: 60_000,
  });
}

/** 供需要自行处理响应流的调用方使用（目前只有 SSE 用到）。 */
export { fetchWithAuth };
