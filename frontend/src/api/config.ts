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
 * 路径带 `/api/config` 前缀，而 `API_BASE_URL` 默认是 `/api`，因此统一用
 * `absolutePath: true` 绕过前缀拼接。
 *
 * 认证头由 `api/client.ts` 统一注入并处理过期刷新，这里不再手工拼
 * `Authorization`——之前各模块自己读 localStorage 拼头，新增接口时极易漏掉。
 */

export async function fetchModelConfig(): Promise<ModelConfig> {
  return request<ModelConfig>("/api/config/model", { absolutePath: true });
}

export async function updateModelConfig(
  payload: ModelConfigUpdate,
): Promise<ModelConfigUpdateResult> {
  return request<ModelConfigUpdateResult>("/api/config/model", {
    method: "PUT",
    json: payload,
    absolutePath: true,
  });
}

export async function fetchProviders(): Promise<ProvidersResponse> {
  return request<ProvidersResponse>("/api/config/providers", { absolutePath: true });
}

export async function testConnection(
  payload: ConnectionTestRequest,
): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>("/api/config/model/test", {
    method: "POST",
    json: payload,
    absolutePath: true,
    // 连接测试要等远端模型服务响应，默认 15 秒超时偏紧，这里放宽。
    timeoutMs: 20_000,
  });
}
