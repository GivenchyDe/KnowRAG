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
  /**
   * 当前生效的向量维度（只读回显）。
   *
   * 维度是**模型的属性**，由后端在实际调用模型时按实测值写回
   * （连接测试测的就是已保存的模型时、以及文档摄取时），因此界面上没有输入框，
   * 更新请求（`ModelConfigUpdate`）里也不存在该字段——后端会显式拒绝它。
   * 测试连接成功后的提示里会带上实测维度。
   */
  embed_dimension: number;

  rerank_provider: string;
  rerank_api_key_masked: string | null;
  rerank_model: string;

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
  // 没有 embed_dimension：后端按模型实测值维护，提交它会被 422 拒绝

  rerank_provider?: string;
  rerank_api_key?: string | null;
  rerank_model?: string;
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
  /**
   * 是否用数据库里**已保存的** Key 测试。
   *
   * 为 true 时后端忽略请求里的 `base_url` / `model`，一律用已保存的值：
   * 那样"测试已保存的 Key"测的就是已保存的那份配置，也避免服务端把 Key
   * 发到调用方指定的任意地址。因此前端在 true 分支里不必（也不应指望）传地址。
   */
  use_saved_key: boolean;
}

/**
 * 三个类别各自的请求类型。
 *
 * 后端是**一个**接口按 `kind` 区分（见 DESIGN_IMPLEMENTATION 第 6.2 节），
 * 因此这里用交叉类型把 `kind` 收窄，而不是复制三份结构：
 * 调用处既能一眼看出"这是测向量模型的"，又不会出现三份彼此漂移的字段定义。
 */
export type ModelConfigTestEmbeddingRequest = ConnectionTestRequest & { kind: "embed" };
export type ModelConfigTestRerankerRequest = ConnectionTestRequest & { kind: "rerank" };

/** 连接测试结果 */
export interface ConnectionTestResult {
  success: boolean;
  code: string;
  message: string;
  /** 诊断信息（实测向量维度、重排分数等）。由后端算出，**不含任何凭据** */
  detail?: Record<string, unknown> | null;
}

/** 连接测试结果的对外名称（与 `ModelConfigTest*` 请求类型成对，便于阅读调用处） */
export type ModelConfigTestResponse = ConnectionTestResult;
