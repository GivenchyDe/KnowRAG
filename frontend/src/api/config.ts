import { request } from "@/api/client";
import type {
  ConnectionTestRequest,
  ConnectionTestResult,
  ModelConfig,
  ModelConfigUpdate,
  ModelConfigUpdateResult,
  ProvidersResponse,
} from "@/types/config";

/**
 * 全局模型配置接口。
 *
 * 路径带 `/api/config` 前缀，而 `API_BASE_URL` 默认是 `/api`，因此这里统一用
 * `absolutePath: true` 绕过前缀——否则会请求到不存在的 `/api/api/config/...`。
 *
 * 认证头由调用方（Pinia store）通过 `token` 参数传入，而不是在这里读取
 * localStorage：这样 token 的来源只有一个（store），也便于将来替换存储方式。
 */

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function fetchModelConfig(token: string | null): Promise<ModelConfig> {
  return request<ModelConfig>("/api/config/model", {
    absolutePath: true,
    headers: authHeaders(token),
  });
}

export async function updateModelConfig(
  payload: ModelConfigUpdate,
  token: string | null,
): Promise<ModelConfigUpdateResult> {
  return request<ModelConfigUpdateResult>("/api/config/model", {
    method: "PUT",
    json: payload,
    absolutePath: true,
    headers: authHeaders(token),
  });
}

export async function fetchProviders(token: string | null): Promise<ProvidersResponse> {
  return request<ProvidersResponse>("/api/config/providers", {
    absolutePath: true,
    headers: authHeaders(token),
  });
}

export async function testConnection(
  payload: ConnectionTestRequest,
  token: string | null,
): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>("/api/config/model/test", {
    method: "POST",
    json: payload,
    absolutePath: true,
    headers: authHeaders(token),
    // 连接测试要等远端模型服务响应，默认 15 秒超时偏紧，这里放宽到 20 秒。
    timeoutMs: 20_000,
  });
}
