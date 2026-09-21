/**
 * HTTP 客户端。
 *
 * 职责边界（遵守 docs/CODING_CONVENTIONS.md 第 3.3 节分层规范）：
 * - 只负责拼装请求、注入认证头、解析响应、把后端错误契约转换成 ApiError；
 * - 不包含任何业务判断，业务逻辑一律放在 store 或页面中。
 *
 * Phase 0 只有 GET /health 一个调用点，因此这里保持最小实现；
 * Phase 1 接入登录后，在这里补 401 自动刷新 token 与跳转登录的处理。
 */

import { ApiError, ErrorCode } from "@/types/errors";
import type { ApiErrorBody } from "@/types/errors";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

/** 默认请求超时（毫秒）。上传、问答等长耗时接口应在调用处单独覆盖。 */
const DEFAULT_TIMEOUT_MS = 15_000;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** 请求体，内部会自动 JSON 序列化；上传文件时改用 body: FormData */
  json?: unknown;
  form?: FormData;
  query?: Record<string, string | number | boolean | undefined | null>;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  /**
   * 跳过 API_BASE_URL 前缀，直接使用传入的路径。
   * 用于 /health 这类不带 /api 前缀的系统接口。
   */
  absolutePath?: boolean;
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

export async function request<TResponse>(
  path: string,
  options: RequestOptions = {},
): Promise<TResponse> {
  const { method = "GET", json, form, query, headers = {}, timeoutMs, signal, absolutePath } =
    options;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs ?? DEFAULT_TIMEOUT_MS);

  // 支持外部取消（如组件卸载）与内部超时同时生效。
  if (signal) {
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  const finalHeaders: Record<string, string> = { Accept: "application/json", ...headers };
  let body: BodyInit | undefined;
  if (form) {
    // 不手动设置 Content-Type：必须让浏览器自动补上 multipart 边界。
    body = form;
  } else if (json !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query, absolutePath), {
      method,
      headers: finalHeaders,
      body,
      signal: controller.signal,
      credentials: "include",
    });
  } catch (error) {
    // 网络层失败与业务失败要区分开，前端提示文案不同。
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError({
        code: ErrorCode.INTERNAL_ERROR,
        message: "请求超时或已取消",
        httpStatus: 0,
      });
    }
    throw new ApiError({
      code: ErrorCode.INTERNAL_ERROR,
      message: "无法连接后端服务，请确认后端已启动",
      httpStatus: 0,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }

  if (!response.ok) {
    const errorBody = await parseErrorBody(response);
    throw new ApiError({
      code: errorBody?.code ?? fallbackCode(response.status),
      message: errorBody?.message ?? `请求失败（HTTP ${response.status}）`,
      httpStatus: response.status,
      traceId: errorBody?.trace_id ?? response.headers.get("X-Trace-Id") ?? undefined,
    });
  }

  // 204 或空响应体（Phase 3 删除文档等接口会用到）。
  if (response.status === 204) {
    return undefined as TResponse;
  }
  const text = await response.text();
  if (!text) {
    return undefined as TResponse;
  }
  return JSON.parse(text) as TResponse;
}
