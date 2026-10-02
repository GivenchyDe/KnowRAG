import { request } from "@/api/client";
import type {
  ConnectionTestRequest,
  ConnectionTestResult,
  ModelConfig,
  ModelConfigTestEmbeddingRequest,
  ModelConfigTestRerankerRequest,
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

/**
 * 连接测试。
 *
 * 三类模型共用**后端同一个接口**（`POST /api/config/model/test`，用 `kind` 区分）。
 * 这里仍然提供三个具名函数：调用处读起来就是"在测向量模型"，
 * 而且各自的参数类型把 `kind` 收窄了，写错类别在编译期就会被拦下。
 *
 * 超时给到 60 秒：连接测试要真实调用一次远程模型（Embedding 会算一次向量、
 * Reranker 会跑一次重排），供应商侧偶发的排队与网络抖动都可能超过默认的 15 秒；
 * 而"服务正常但响应慢"被误判为不可达，会让用户去改本来正确的配置。
 */
const TEST_TIMEOUT_MS = 60_000;

function requestTest(payload: ConnectionTestRequest): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>("/api/config/model/test", {
    method: "POST",
    json: payload,
    absolutePath: true,
    timeoutMs: TEST_TIMEOUT_MS,
  });
}

export async function testLlmConnection(
  payload: Omit<ConnectionTestRequest, "kind">,
): Promise<ConnectionTestResult> {
  return requestTest({ ...payload, kind: "llm" });
}

export async function testEmbeddingConnection(
  payload: Omit<ModelConfigTestEmbeddingRequest, "kind">,
): Promise<ConnectionTestResult> {
  return requestTest({ ...payload, kind: "embed" });
}

export async function testRerankerConnection(
  payload: Omit<ModelConfigTestRerankerRequest, "kind">,
): Promise<ConnectionTestResult> {
  return requestTest({ ...payload, kind: "rerank" });
}
