/**
 * 全局模型配置类型。
 *
 * 字段与 `docs/DESIGN_IMPLEMENTATION.md` 第 6.2 节的 API 契约一一对应，
 * 后端 `backend/app/schemas/config.py` 是唯一来源；接口变更时必须同步这里。
 */

/** 全局模型配置（读取），对应 GET /api/config/model */
export interface ModelConfig {
  llm_provider: string;
  /** 脱敏后的 Key，形如 `sk-****abcd`；未填写为 null。后端永不返回明文 */
  llm_api_key_masked: string | null;
  llm_base_url: string | null;
  llm_model: string;
  llm_temperature: number;
  llm_max_tokens: number;

  embed_provider: string;
  embed_api_key_masked: string | null;
  embed_model: string;
  embed_model_path: string | null;
  embed_dimension: number;

  rerank_provider: string;
  rerank_api_key_masked: string | null;
  rerank_model: string;
  rerank_model_path: string | null;

  updated_at: string | null;
}

/**
 * 更新请求。
 *
 * 语义（与后端约定一致，见 `ModelConfigUpdate` 的文档注释）：
 * - 字段**不出现**在对象里 → 保持原值不变；
 * - API Key 字段传 `""` → 显式清除已保存的 Key；
 * - API Key 字段传 `null` 或省略 → 保持原 Key。
 */
export interface ModelConfigUpdate {
  llm_provider?: string;
  llm_api_key?: string | null;
  llm_base_url?: string | null;
  llm_model?: string;
  llm_temperature?: number;
  llm_max_tokens?: number;

  embed_provider?: string;
  embed_api_key?: string | null;
  embed_model?: string;
  embed_model_path?: string | null;
  embed_dimension?: number;

  rerank_provider?: string;
  rerank_api_key?: string | null;
  rerank_model?: string;
  rerank_model_path?: string | null;
}

/** 更新响应，对应 PUT /api/config/model */
export interface ModelConfigUpdateResult {
  status: string;
  /** Embedding 配置变化时为 true，前端据此提示「需要重建知识库索引」 */
  index_stale: boolean;
  message: string;
}

/** provider 目录项。前端不硬编码 provider 与模型名，一律从接口获取 */
export interface ProviderOption {
  value: string;
  label: string;
  default_base_url: string | null;
  default_model: string;
  suggested_models: string[];
}

/** 支持的 provider 列表，对应 GET /api/config/providers */
export interface ProvidersResponse {
  llm: ProviderOption[];
  embed: ProviderOption[];
  rerank: ProviderOption[];
}

/** 连接测试的模型类别 */
export type ConnectionTestKind = "llm" | "embed" | "rerank";

/** 连接测试请求，对应 POST /api/config/model/test */
export interface ConnectionTestRequest {
  kind: ConnectionTestKind;
  provider: string;
  api_key?: string | null;
  base_url?: string | null;
  model?: string | null;
}

/** 连接测试结果 */
export interface ConnectionTestResult {
  success: boolean;
  code: string;
  message: string;
}
