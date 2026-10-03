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
  /** 向量模型的接口地址。只有 provider 为 custom 时才有意义（也是界面是否显示输入框的判据） */
  embed_base_url: string | null;
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
  /** 重排模型的接口地址。同 embed_base_url：只有 custom 需要 */
  rerank_base_url: string | null;
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
  /** 只有 provider 为 custom 时才提交（后端也会在切换 provider 时按目录兜底写入） */
  embed_base_url?: string | null;
  embed_model?: string;
  // 没有 embed_dimension：后端按模型实测值维护，提交它会被 422 拒绝

  rerank_provider?: string;
  rerank_api_key?: string | null;
  /** 同 embed_base_url */
  rerank_base_url?: string | null;
  rerank_model?: string;
}

/** 更新响应，对应 PUT /api/config/model */
export interface ModelConfigUpdateResult {
  status: string;
  /** Embedding 配置变化时为 true，前端据此提示「需要重建知识库索引」 */
  index_stale: boolean;
  message: string;
}

/**
 * provider 目录项。前端不硬编码 provider 与模型名，一律从接口获取。
 *
 * 模型名是**纯手输**：这里曾经有 `models`（预设列表）与 `ProviderModelOption`，
 * 供 `<datalist>` 做建议下拉；2026-10-04 删除，因为那个原生箭头无法用 CSS 隐藏、
 * 界面改成了手输，列表就没有消费方了。将来要做建议列表，应当自绘候选面板或改用
 * Element Plus 的 `el-autocomplete`，而不要再搬回原生 `datalist`。
 */
export interface ProviderOption {
  value: string;
  label: string;
  /**
   * 默认接口地址。
   *
   * `null` 表示"没有可直接使用的默认地址"，此时分两种情况，
   * **不能用它来判断界面是否要显示地址输入框**（那会让 qwen 也被要求填地址）：
   *   - 端点由后端代码固定（qwen 的向量与重排）→ 用户不需要也不能填；
   *   - 必须由用户填写（value === "custom"）→ 界面必须给输入框。
   */
  default_base_url: string | null;
  /** custom 为空字符串：没有可推荐的默认模型，必须由用户填写 */
  default_model: string;
  /**
   * 该 provider 的地址是否必须由用户填写（当前只有 custom 为 true）。
   *
   * 界面据此决定显不显示地址输入框——**不要**用 `default_base_url === null` 代替：
   * qwen 的向量/重排也没有可展示的地址，但端点由后端固定，不需要用户填。
   */
  requires_base_url: boolean;
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
