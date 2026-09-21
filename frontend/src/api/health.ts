import { request } from "@/api/client";
import type { HealthResponse } from "@/types/api";

/**
 * 系统接口。
 *
 * 注意：/health 不在 /api 前缀下（见 docs/DESIGN_IMPLEMENTATION.md 第 12 节 Phase 0 验收），
 * 因此通过 absolutePath 跳过 API_BASE_URL，请求根路径 /health；
 * 开发环境由 Vite 代理、生产环境由 Nginx 反代到后端，前端不需要知道后端地址。
 */
export async function fetchHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health", { absolutePath: true, timeoutMs: 5_000 });
}
