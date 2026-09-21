/**
 * HTTP 客户端。
 *
 * 职责边界（遵守 docs/CODING_CONVENTIONS.md 第 3.3 节分层规范）：
 * - 负责拼装请求、**统一注入认证头**、处理 token 过期与刷新、解析响应、
 *   把后端错误契约转换成 ApiError；
 * - 不包含任何业务判断，业务逻辑一律放在 store 或页面中。
 *
 * 为什么认证逻辑放在这一层而不是各 api 模块里：
 * 之前每个 api 模块各自从 localStorage 读 token 并手工拼 `Authorization` 头，
 * 结果是（1）新增接口时容易忘记带 token；（2）没有任何 401 恢复机制——
 * access token 只有 30 分钟有效期，过期后侧边栏会话列表变空、页面报错，
 * 但**不会跳回登录页**，用户被卡在「看似登录着却什么都加载不出来」的状态。
 * 现在这些逻辑集中在这里，`fetchWithAuth` 是唯一的认证请求入口。
 */

import { getAccessToken, getRefreshToken, isAccessTokenExpiring, saveTokens } from "@/auth/tokenStorage";
import { ApiError, ErrorCode } from "@/types/errors";
import type { ApiErrorBody } from "@/types/errors";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** 默认请求超时（毫秒）。上传、问答等长耗时接口应在调用处单独覆盖。 */
const DEFAULT_TIMEOUT_MS = 15_000;

/** 刷新 token 的超时。它只是一个轻量 POST，不需要长超时。 */
const REFRESH_TIMEOUT_MS = 10_000;

/**
 * 会话彻底失效时的回调。由 main.ts 注册（跳转登录页 + 提示原因）。
 *
 * 用回调而不是在 client 里直接操作 router/store，是为了避免模块循环依赖：
 * auth store 依赖 client 发请求，client 再反过来依赖 store 就成环了。
 */
type UnauthorizedHandler = (reason: string) => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

export function setUnauthorizedHandler(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler;
}

function notifyUnauthorized(reason: string): void {
  if (unauthorizedHandler) {
    unauthorizedHandler(reason);
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** 请求体，内部会自动 JSON 序列化；上传文件时改用 form */
  json?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  /**
   * 跳过 API_BASE_URL 前缀，直接使用传入的路径。
   * 用于 /health、/auth/* 这类不带 /api 前缀的接口。
   */
  absolutePath?: boolean;
  /** 不附加 Authorization 头。登录、注册、刷新这类接口用 */
  skipAuth?: boolean;
}

/** 把查询参数拼到路径上，自动跳过 undefined / null。 */
function buildUrl(path: string, query?: RequestOptions["query"], absolutePath = false): string {
  const url = absolutePath ? path : `${API_BASE_URL}${path}`;
  if (!query) {
    return url;
  }
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) {
      search.append(key, String(value));
    }
  }
  const queryString = search.toString();
  return queryString ? `${url}?${queryString}` : url;
}

/** 读取后端错误响应体；非 JSON 或字段缺失时返回 undefined。 */
async function parseErrorBody(response: Response): Promise<ApiErrorBody | undefined> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object") {
      const body = data as Partial<ApiErrorBody>;
      if (typeof body.code === "string" && typeof body.message === "string") {
        return { code: body.code, message: body.message, trace_id: body.trace_id };
      }
    }
    return undefined;
  } catch {
    return undefined;
  }
}

/** 根据 HTTP 状态码推断错误码，用于后端未按契约返回错误体时的兜底。 */
function fallbackCode(httpStatus: number): string {
  if (httpStatus === 401) return ErrorCode.UNAUTHORIZED;
  if (httpStatus === 403) return ErrorCode.FORBIDDEN;
  if (httpStatus === 404) return ErrorCode.RESOURCE_NOT_FOUND;
  if (httpStatus === 422) return ErrorCode.VALIDATION_ERROR;
  if (httpStatus === 429) return ErrorCode.RATE_LIMITED;
  return ErrorCode.INTERNAL_ERROR;
}

/** 组合超时与外部取消信号。 */
function makeAbortController(timeoutMs: number, external?: AbortSignal): AbortController {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  controller.signal.addEventListener("abort", () => window.clearTimeout(timer), { once: true });
  if (external) {
    if (external.aborted) {
      controller.abort();
    } else {
      external.addEventListener("abort", () => controller.abort(), { once: true });
    }
  }
  return controller;
}

/** 组装请求头与请求体。 */
function buildInit(options: RequestOptions, token: string | null): RequestInit {
  const headers: Record<string, string> = { Accept: "application/json", ...options.headers };
  if (token && !options.skipAuth) {
    headers.Authorization = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (options.form) {
    // 不手动设置 Content-Type：必须让浏览器自动补上 multipart 边界。
    body = options.form;
  } else if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.json);
  }

  const controller = makeAbortController(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, options.signal);
  return { method: options.method ?? "GET", headers, body, signal: controller.signal, credentials: "include" };
}

/** 网络层异常 → ApiError。 */
function toNetworkError(error: unknown): ApiError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return new ApiError({
      code: ErrorCode.INTERNAL_ERROR,
      message: "请求超时或已取消",
      httpStatus: 0,
    });
  }
  return new ApiError({
    code: ErrorCode.INTERNAL_ERROR,
    message: "无法连接后端服务，请确认后端已启动",
    httpStatus: 0,
  });
}

/**
 * 并发去重：多个请求同时发现 token 过期时，只发起一次刷新。
 * 否则页面上 5 个并行请求会各刷新一次，产生 5 次无效的 token 轮换
 * （refresh token 是轮换式的，后发的可能因为前一次已换掉而失败）。
 */
let refreshPromise: Promise<boolean> | null = null;

/** 用 refresh token 换取新的 token 对，成功返回 true。 */
export function refreshTokens(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return Promise.resolve(false);
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        signal: makeAbortController(REFRESH_TIMEOUT_MS).signal,
      });
      if (!response.ok) {
        return false;
      }
      const tokens = (await response.json()) as { access_token: string; refresh_token: string };
      saveTokens({ ...tokens, token_type: "bearer" });
      return true;
    } catch {
      // 网络问题导致的刷新失败也返回 false，由调用方决定是否登出。
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

/**
 * 发起一个带认证的请求。
 *
 * 两层 token 保护：
 * 1. **提前刷新**——发请求前若发现 access token 即将过期（或已过期），先静默刷新。
 *    这样正常情况下用户永远不会看到 401；
 * 2. **事后重试**——仍收到 401 时（例如 token 被服务端判定失效、或 exp 解析失败），
 *    刷新一次并重试原请求。只重试一次，避免刷新失败时陷入死循环。
 */
export async function fetchWithAuth(
  path: string,
  options: RequestOptions = {},
): Promise<Response> {
  const url = buildUrl(path, options.query, options.absolutePath);
  const needsAuth = !options.skipAuth;

  if (needsAuth && isAccessTokenExpiring()) {
    const refreshed = await refreshTokens();
    if (!refreshed) {
      // 连 refresh token 都没有或已失效：不必再发这次注定 401 的请求。
      notifyUnauthorized("登录已过期，请重新登录");
      throw new ApiError({
        code: ErrorCode.UNAUTHORIZED,
        message: "登录已过期，请重新登录",
        httpStatus: 401,
      });
    }
  }

  let response: Response;
  try {
    response = await fetch(url, buildInit(options, getAccessToken()));
  } catch (error) {
    throw toNetworkError(error);
  }

  if (response.status !== 401 || !needsAuth) {
    return response;
  }

  // 走到这里说明 token 被服务端拒绝。刷新一次再重试。
  const refreshed = await refreshTokens();
  if (!refreshed) {
    notifyUnauthorized("登录已过期，请重新登录");
    return response;
  }

  try {
    return await fetch(url, buildInit(options, getAccessToken()));
  } catch (error) {
    throw toNetworkError(error);
  }
}

/** 把非 2xx 响应转换成 ApiError。 */
async function throwIfNotOk(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }
  const errorBody = await parseErrorBody(response);
  throw new ApiError({
    code: errorBody?.code ?? fallbackCode(response.status),
    message: errorBody?.message ?? `请求失败（HTTP ${response.status}）`,
    httpStatus: response.status,
    traceId: errorBody?.trace_id ?? response.headers.get("X-Trace-Id") ?? undefined,
  });
}

/** 发起请求并把响应解析为 JSON。 */
export async function request<TResponse>(
  path: string,
  options: RequestOptions = {},
): Promise<TResponse> {
  const response = await fetchWithAuth(path, options);
  await throwIfNotOk(response);

  // 204 或空响应体（删除类接口会用到）。
  if (response.status === 204) {
    return undefined as TResponse;
  }
  const text = await response.text();
  if (!text) {
    return undefined as TResponse;
  }
  return JSON.parse(text) as TResponse;
}
