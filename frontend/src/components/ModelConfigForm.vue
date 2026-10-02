<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import TestConnectionButton from "@/components/TestConnectionButton.vue";
import { useConfigStore } from "@/stores/config";
import type { ModelConfigUpdate, ProviderOption } from "@/types/config";

/**
 * 模型配置表单。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「模型设置页」——设置项分组清晰、
 * 不要把所有表单堆成一大片、每组像轻量 section 而不是多层嵌套卡片。
 *
 * 三个关键交互约定：
 * 1. **API Key 不回显明文**。输入框留空表示「保持已保存的 Key 不变」；
 *    用户点「替换」后输入才会作为新 Key 提交；点「清除」会显式提交空字符串。
 *    这个三态（保持 / 替换 / 清除）与后端 `ModelConfigUpdate` 的语义严格对应。
 * 2. **只提交有改动的字段**。后端把「字段未提供」解释为「保持原值」，
 *    因此只发送改动项可以避免覆盖掉其他标签页或其他用户在期间做的修改。
 * 3. **模型名是纯手动输入**（曾经用过 `<input list>` + `<datalist>` 的
 *    「预设下拉 + 手动输入」混合方案，现已撤销）。撤销原因不是取舍偏好，而是
 *    原生控件下这两件事不可兼得：`<input list>` 右端的原生箭头**无法用 CSS 隐藏**
 *    （2026-10-02 在 Chrome 154 上实测四种手法全部无效，见模板里的详细注释）。
 *    既然箭头去不掉、又和本项目的控件语言冲突，就改成只要"手输"：
 *    推荐模型通过 placeholder 提示（取值仍来自后端目录，前端不硬编码模型名）。
 *    后端目录里的 `models` / `recommended` 字段保留未动——它是接口数据，
 *    将来若换成自绘候选面板可以直接用。
 */

const configStore = useConfigStore();

/** 本地草稿。留空表示「不修改该项」。 */
const draft = reactive({
  llmProvider: "",
  llmApiKey: "",
  llmBaseUrl: "",
  llmModel: "",
  llmTemperature: 0.1,
  llmMaxTokens: 2048,
  embedProvider: "",
  embedApiKey: "",
  embedBaseUrl: "",
  embedModel: "",
  rerankProvider: "",
  rerankApiKey: "",
  rerankBaseUrl: "",
  rerankModel: "",
});

/**
 * 用户是否手动改过某类别的模型名。
 *
 * 只用于「切换 Provider 时是否自动填充默认模型」这一条交互：没手动改过（输入框里
 * 还是上一个 provider 的默认值）就覆盖成新 provider 的默认值；手动改过则保留用户的选择
 * （他可能填了一个预设列表里没有的 ID，覆盖掉等于替他做决定）。
 *
 * 判据是 `@input` 事件：**只有真实输入会触发它**，代码里给 v-model 赋值不会，
 * 因此不必额外维护"这次改动是程序做的还是人做的"这类容易出错的状态。
 */
const modelEdited = reactive({ llm: false, embed: false, rerank: false });

/** 是否正在替换某把 Key（点击「替换」后为 true，用于切换输入框与脱敏展示）。 */
const replacingKey = reactive({ llm: false, embed: false, rerank: false });
/** 是否要清除某把 Key。与替换互斥，提交时传空字符串。 */
const clearingKey = reactive({ llm: false, embed: false, rerank: false });

const formError = ref<string | null>(null);
const successMessage = ref<string | null>(null);

const config = computed(() => configStore.config);
const providers = computed(() => configStore.providers);

/** 从原始配置同步草稿。切换 provider 时也会调用，用于刷新默认值。 */
function syncDraft(): void {
  const current = config.value;
  if (!current) {
    return;
  }
  draft.llmProvider = current.llm_provider;
  draft.llmBaseUrl = current.llm_base_url ?? "";
  draft.llmModel = current.llm_model;
  draft.llmTemperature = current.llm_temperature;
  draft.llmMaxTokens = current.llm_max_tokens;

  draft.embedProvider = current.embed_provider;
  draft.embedBaseUrl = current.embed_base_url ?? "";
  draft.embedModel = current.embed_model;

  draft.rerankProvider = current.rerank_provider;
  draft.rerankBaseUrl = current.rerank_base_url ?? "";
  draft.rerankModel = current.rerank_model;

  draft.llmApiKey = "";
  draft.embedApiKey = "";
  draft.rerankApiKey = "";
  replacingKey.llm = false;
  replacingKey.embed = false;
  replacingKey.rerank = false;
  clearingKey.llm = false;
  clearingKey.embed = false;
  clearingKey.rerank = false;
  // 草稿已与后端同步，"手动改过"这个标记也随之复位：下一次切换 provider
  // 应当重新按默认值填充，而不是继承上一次会话的编辑痕迹。
  modelEdited.llm = false;
  modelEdited.embed = false;
  modelEdited.rerank = false;
}

onMounted(async () => {
  await Promise.all([configStore.load(), configStore.loadProviders()]);
  syncDraft();
});

/** 某类别的 provider 选项。取值一律来自后端目录，前端不硬编码 provider 与模型名。 */
function optionsFor(kind: "llm" | "embed" | "rerank"): ProviderOption[] {
  return providers.value?.[kind] ?? [];
}

/** 当前 provider 的目录项，用于取预设模型与默认 base_url。 */
function currentOption(kind: "llm" | "embed" | "rerank", value: string): ProviderOption | undefined {
  return optionsFor(kind).find((option) => option.value === value);
}

/**
 * 该 provider 是否必须由用户填写接口地址（当前为 custom）。
 *
 * 取值来自目录的 `requires_base_url`，而不是在前端判断 provider 叫什么——
 * 前端不硬编码 provider 名（README 3.2）。
 */
function requiresBaseUrl(kind: "llm" | "embed" | "rerank"): boolean {
  return currentOption(kind, providerOf(kind))?.requires_base_url ?? false;
}

/** 用户在某类别的模型输入框里真实输入过内容。 */
function markModelEdited(kind: "llm" | "embed" | "rerank"): void {
  modelEdited[kind] = true;
}

/**
 * 模型名输入框的占位文案。
 *
 * 模型名是**纯手动输入**（不用 `<datalist>`，原因见模板里的注释），因此在框里
 * 给出该 provider 的默认/推荐模型作为示例——取值来自后端目录的 `default_model`，
 * 前端仍然不硬编码任何模型名。没有默认值的 provider（custom）就只说"手动输入"。
 */
function modelPlaceholder(kind: "llm" | "embed" | "rerank"): string {
  const defaultModel = currentOption(kind, providerOf(kind))?.default_model ?? "";
  return defaultModel ? `如 ${defaultModel}` : "手动输入模型 ID";
}

/**
 * 切换 provider 时把模型名与 base_url 换成该 provider 的默认值，避免内部不一致
 * （例如"provider 已是 qwen、模型名还是 deepseek-v4-pro"）。
 *
 * **例外**：模型名被用户手动改过就不覆盖——他可能填了一个预设列表里没有的 ID，
 * 替用户改回默认值等于丢掉他刚敲进去的东西。判据是 `modelEdited`，
 * 由输入框的 `@input` 置位（只有真实输入会触发）。
 * 注意这里只对"模型名"做例外：地址随 provider 变化是必须的，
 * 否则会拿 A 家的地址去请求 B 家。
 */
function onProviderChange(kind: "llm" | "embed" | "rerank"): void {
  const option = currentOption(kind, providerOf(kind));
  if (!option) {
    return;
  }
  if (kind === "llm") {
    if (!modelEdited.llm) draft.llmModel = option.default_model;
    draft.llmBaseUrl = option.default_base_url ?? "";
  } else if (kind === "embed") {
    if (!modelEdited.embed) draft.embedModel = option.default_model;
    draft.embedBaseUrl = option.default_base_url ?? "";
  } else {
    if (!modelEdited.rerank) draft.rerankModel = option.default_model;
    draft.rerankBaseUrl = option.default_base_url ?? "";
  }
}

/**
 * 构造更新请求：只包含真正发生变化的字段。
 *
 * 注意 API Key 的三态处理——只有用户明确点了「替换」且填了值，或点了「清除」，
 * 才会把该字段放进请求；否则整个字段不出现，后端保持原 Key。
 */
function buildPayload(): ModelConfigUpdate {
  const current = config.value;
  const payload: ModelConfigUpdate = {};
  if (!current) {
    return payload;
  }

  if (draft.llmProvider !== current.llm_provider) payload.llm_provider = draft.llmProvider;
  if (draft.llmBaseUrl !== (current.llm_base_url ?? "")) payload.llm_base_url = draft.llmBaseUrl || null;
  if (draft.llmModel !== current.llm_model) payload.llm_model = draft.llmModel;
  if (draft.llmTemperature !== current.llm_temperature) payload.llm_temperature = draft.llmTemperature;
  if (draft.llmMaxTokens !== current.llm_max_tokens) payload.llm_max_tokens = draft.llmMaxTokens;

  if (draft.embedProvider !== current.embed_provider) payload.embed_provider = draft.embedProvider;
  if (draft.embedBaseUrl !== (current.embed_base_url ?? "")) {
    payload.embed_base_url = draft.embedBaseUrl || null;
  }
  if (draft.embedModel !== current.embed_model) payload.embed_model = draft.embedModel;
  // 不提交 embed_dimension：向量维度由后端按模型实测值维护，见 types/config.ts 的说明。

  if (draft.rerankProvider !== current.rerank_provider) payload.rerank_provider = draft.rerankProvider;
  if (draft.rerankBaseUrl !== (current.rerank_base_url ?? "")) {
    payload.rerank_base_url = draft.rerankBaseUrl || null;
  }
  if (draft.rerankModel !== current.rerank_model) payload.rerank_model = draft.rerankModel;

  if (clearingKey.llm) {
    payload.llm_api_key = "";
  } else if (replacingKey.llm && draft.llmApiKey.trim()) {
    payload.llm_api_key = draft.llmApiKey.trim();
  }
  if (clearingKey.embed) {
    payload.embed_api_key = "";
  } else if (replacingKey.embed && draft.embedApiKey.trim()) {
    payload.embed_api_key = draft.embedApiKey.trim();
  }
  if (clearingKey.rerank) {
    payload.rerank_api_key = "";
  } else if (replacingKey.rerank && draft.rerankApiKey.trim()) {
    payload.rerank_api_key = draft.rerankApiKey.trim();
  }

  return payload;
}

const hasChanges = computed(() => Object.keys(buildPayload()).length > 0);

async function handleSave(): Promise<void> {
  formError.value = null;
  successMessage.value = null;
  try {
    const result = await configStore.save(buildPayload());
    syncDraft();
    successMessage.value = result.message;
  } catch {
    formError.value = configStore.errorMessage ?? "保存失败，请稍后重试";
  }
}

/**
 * 某类别是否已保存过 Key。
 *
 * 直接由后端返回的 `*_api_key_masked` 推导，而不是另存一份本地布尔：
 * 后者会在「保存成功但本地状态没同步」时与真实情况不一致（例如用户在
 * 另一个标签页改了配置），而这种不一致的表现正是"以为能测、点下去却报未保存"。
 */
function hasSavedKey(kind: "llm" | "embed" | "rerank"): boolean {
  return Boolean(maskedOf(kind));
}

function startReplace(which: "llm" | "embed" | "rerank"): void {
  replacingKey[which] = true;
  clearingKey[which] = false;
  if (which === "llm") draft.llmApiKey = "";
  if (which === "embed") draft.embedApiKey = "";
  if (which === "rerank") draft.rerankApiKey = "";
}

function startClear(which: "llm" | "embed" | "rerank"): void {
  clearingKey[which] = true;
  replacingKey[which] = false;
  if (which === "llm") draft.llmApiKey = "";
  if (which === "embed") draft.embedApiKey = "";
  if (which === "rerank") draft.rerankApiKey = "";
}

function cancelKeyEdit(which: "llm" | "embed" | "rerank"): void {
  replacingKey[which] = false;
  clearingKey[which] = false;
  if (which === "llm") draft.llmApiKey = "";
  if (which === "embed") draft.embedApiKey = "";
  if (which === "rerank") draft.rerankApiKey = "";
}

/** 某类别已保存的脱敏 Key 展示文案。 */
function maskedOf(kind: "llm" | "embed" | "rerank"): string | null {
  const current = config.value;
  if (!current) return null;
  if (kind === "llm") return current.llm_api_key_masked;
  if (kind === "embed") return current.embed_api_key_masked;
  return current.rerank_api_key_masked;
}

/** 某类别当前选中的 provider 取值。 */
function providerOf(kind: "llm" | "embed" | "rerank"): string {
  if (kind === "llm") return draft.llmProvider;
  return kind === "embed" ? draft.embedProvider : draft.rerankProvider;
}
</script>

<template>
  <div class="form-wrap">
    <p v-if="configStore.loading" class="state state--loading">正在加载配置…</p>

    <template v-else-if="config">
      <!-- ============ LLM ============ -->
      <section class="kr-panel section">
        <header class="section__head">
          <h2 class="section__title">对话模型（LLM）</h2>
          <p class="section__desc">用于生成回答。</p>
        </header>

        <!-- 三个卡片的结构完全一致：Provider 与「模型名」两列并排，
             Base URL 占满整行、且只在「自定义端点」时出现（判据见 requiresBaseUrl）。 -->
        <div class="grid">
          <label class="kr-field">
            <span class="kr-label">Provider</span>
            <span class="select">
              <select v-model="draft.llmProvider" class="kr-input" @change="onProviderChange('llm')">
                <option v-for="option in optionsFor('llm')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="kr-field">
            <span class="kr-label">模型名</span>
            <!-- 模型名：**纯手动输入，不用 `<datalist>`**。
                 原因：`<input list>` 右端的原生箭头由浏览器自绘（形状/颜色/与边框的距离
                 都不受控，深色主题下也不跟 token），而它**无法用 CSS 隐藏**——
                 2026-10-02 在 Chrome 154 上实测四种手法全部无效
                 （::-webkit-calendar-picker-indicator / ::-webkit-list-button /
                 appearance: none / opacity: 0，加与不加逐像素完全相同）。
                 既然"有建议列表"与"没有箭头"在原生控件下不可兼得，这里选择不要箭头：
                 模型名手输，推荐模型通过占位文案提示（值仍来自后端目录）。 -->
            <input
              v-model="draft.llmModel"
              class="kr-input"
              type="text"
              :placeholder="modelPlaceholder('llm')"
              @input="markModelEdited('llm')"
            />
          </label>

          <!-- 官方预设 provider（deepseek / qwen / zhipu / mimo / siliconflow）的地址
               由后端目录给出，因此这里**不显示**输入框：填了不会生效的配置项一个都不留。
               只有 custom 需要用户自己填地址，此时后端也会要求它必填。 -->
          <Transition name="reveal">
            <label v-if="requiresBaseUrl('llm')" class="kr-field field--wide">
              <span class="kr-label">接口地址（Base URL）</span>
              <input
                v-model="draft.llmBaseUrl"
                class="kr-input"
                type="text"
                placeholder="必填，如 https://your-host/v1"
              />
              <span class="kr-help">需为 OpenAI 兼容端点，调用时自动拼接 /chat/completions</span>
            </label>
          </Transition>

          <label class="kr-field">
            <span class="kr-label">Temperature</span>
            <input
              v-model.number="draft.llmTemperature"
              class="kr-input"
              type="number"
              min="0"
              max="2"
              step="0.1"
            />
            <span class="kr-help">知识库问答建议 0.1–0.3，保持稳定、少发散</span>
          </label>

          <label class="kr-field">
            <span class="kr-label">Max Tokens</span>
            <input
              v-model.number="draft.llmMaxTokens"
              class="kr-input"
              type="number"
              min="1"
              max="131072"
              step="256"
            />
          </label>
        </div>

        <!-- 凭据操作栏：**左组 | 竖线 | 右组**，容器两端对齐。
             左组＝「API Key 标签（不换行、不收缩）+ 值胶囊 + 语义色行内操作」，
             右组＝「测试连接」。三个分区的这一栏结构与样式完全一致，差异只有 kind。 -->
        <div class="credential">
          <div class="key-bar">
            <div class="key-bar__left">
              <span class="kr-label key-bar__label">API Key</span>

              <template v-if="clearingKey.llm">
                <span class="key-badge key-badge--warning">已标记为清除，保存后生效</span>
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('llm')"
                >
                  撤销
                </button>
              </template>

              <template v-else-if="replacingKey.llm">
                <input
                  v-model="draft.llmApiKey"
                  class="kr-input key-input"
                  type="password"
                  autocomplete="off"
                  placeholder="粘贴新的 API Key"
                />
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('llm')"
                >
                  取消
                </button>
              </template>

              <template v-else-if="maskedOf('llm')">
                <code class="key-badge">{{ maskedOf("llm") }}</code>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('llm')"
                >
                  替换
                </button>
                <button
                  class="kr-btn kr-btn--outline-danger kr-btn--compact"
                  type="button"
                  @click="startClear('llm')"
                >
                  清除
                </button>
              </template>

              <!-- 未配置：值与已保存时用**同一个胶囊**（只有文字色与字体不同），
                   行内操作只有「填写」（没有 Key 可清除）。 -->
              <template v-else>
                <span class="key-badge key-badge--empty">未配置</span>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('llm')"
                >
                  填写
                </button>
              </template>
            </div>

            <span class="key-bar__sep" aria-hidden="true"></span>

            <div class="key-bar__right">
              <!-- 测试连接：三类模型共用同一个组件，按钮为**主色填充**
                   （.kr-btn--primary.kr-btn--compact），与左侧描边按钮同为 32px。 -->
              <TestConnectionButton
                test-type="llm"
                :provider="draft.llmProvider"
                :model="draft.llmModel"
                :base-url="draft.llmBaseUrl"
                :api-key="replacingKey.llm ? draft.llmApiKey : ''"
                :has-saved-key="hasSavedKey('llm')"
                :key-cleared="clearingKey.llm"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Embedding ============ -->
      <section class="kr-panel section">
        <header class="section__head">
          <h2 class="section__title">向量模型（Embedding）</h2>
          <p class="section__desc">将文本转为向量，修改后需重建索引。</p>
        </header>

        <div class="grid">
          <label class="kr-field">
            <span class="kr-label">Provider</span>
            <span class="select">
              <select v-model="draft.embedProvider" class="kr-input" @change="onProviderChange('embed')">
                <option v-for="option in optionsFor('embed')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="kr-field">
            <span class="kr-label">模型名</span>
            <input
              v-model="draft.embedModel"
              class="kr-input"
              type="text"
              :placeholder="modelPlaceholder('embed')"
              @input="markModelEdited('embed')"
            />
          </label>

          <!-- 与 LLM 完全相同的规则：官方预设隐藏、custom 显示且必填。
               注意：qwen 的向量端点由后端代码固定（DashScope 专属端点），
               因此它在目录里的 default_base_url 是 null，但它**不是** custom，
               不会显示输入框——判据是 requires_base_url，而不是"地址是否为空"。 -->
          <Transition name="reveal">
            <label v-if="requiresBaseUrl('embed')" class="kr-field field--wide">
              <span class="kr-label">接口地址（Base URL）</span>
              <input
                v-model="draft.embedBaseUrl"
                class="kr-input"
                type="text"
                placeholder="必填，如 https://your-host/v1"
              />
              <span class="kr-help">需为 OpenAI 兼容端点，调用时自动拼接 /embeddings</span>
            </label>
          </Transition>
        </div>

        <div class="credential">
          <div class="key-bar">
            <div class="key-bar__left">
              <span class="kr-label key-bar__label">API Key</span>

              <template v-if="clearingKey.embed">
                <span class="key-badge key-badge--warning">已标记为清除，保存后生效</span>
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('embed')"
                >
                  撤销
                </button>
              </template>

              <template v-else-if="replacingKey.embed">
                <input
                  v-model="draft.embedApiKey"
                  class="kr-input key-input"
                  type="password"
                  autocomplete="off"
                  placeholder="粘贴新的 API Key"
                />
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('embed')"
                >
                  取消
                </button>
              </template>

              <template v-else-if="maskedOf('embed')">
                <code class="key-badge">{{ maskedOf("embed") }}</code>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('embed')"
                >
                  替换
                </button>
                <button
                  class="kr-btn kr-btn--outline-danger kr-btn--compact"
                  type="button"
                  @click="startClear('embed')"
                >
                  清除
                </button>
              </template>

              <template v-else>
                <span class="key-badge key-badge--empty">未配置</span>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('embed')"
                >
                  填写
                </button>
              </template>
            </div>

            <span class="key-bar__sep" aria-hidden="true"></span>

            <div class="key-bar__right">
              <TestConnectionButton
                test-type="embed"
                :provider="draft.embedProvider"
                :model="draft.embedModel"
                :base-url="draft.embedBaseUrl"
                :api-key="replacingKey.embed ? draft.embedApiKey : ''"
                :has-saved-key="hasSavedKey('embed')"
                :key-cleared="clearingKey.embed"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- ============ Reranker ============ -->
      <section class="kr-panel section">
        <header class="section__head">
          <h2 class="section__title">重排模型（Reranker）</h2>
          <p class="section__desc">对检索结果重排序，修改后无需重建索引。</p>
        </header>

        <div class="grid">
          <label class="kr-field">
            <span class="kr-label">Provider</span>
            <span class="select">
              <select v-model="draft.rerankProvider" class="kr-input" @change="onProviderChange('rerank')">
                <option v-for="option in optionsFor('rerank')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="kr-field">
            <span class="kr-label">模型名</span>
            <input
              v-model="draft.rerankModel"
              class="kr-input"
              type="text"
              :placeholder="modelPlaceholder('rerank')"
              @input="markModelEdited('rerank')"
            />
          </label>

          <Transition name="reveal">
            <label v-if="requiresBaseUrl('rerank')" class="kr-field field--wide">
              <span class="kr-label">接口地址（Base URL）</span>
              <input
                v-model="draft.rerankBaseUrl"
                class="kr-input"
                type="text"
                placeholder="必填，如 https://your-host/v1"
              />
              <span class="kr-help">需提供 Cohere / Jina 风格的 POST /rerank 接口</span>
            </label>
          </Transition>
        </div>

        <div class="credential">
          <div class="key-bar">
            <div class="key-bar__left">
              <span class="kr-label key-bar__label">API Key</span>

              <template v-if="clearingKey.rerank">
                <span class="key-badge key-badge--warning">已标记为清除，保存后生效</span>
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('rerank')"
                >
                  撤销
                </button>
              </template>

              <template v-else-if="replacingKey.rerank">
                <input
                  v-model="draft.rerankApiKey"
                  class="kr-input key-input"
                  type="password"
                  autocomplete="off"
                  placeholder="粘贴新的 API Key"
                />
                <button
                  class="kr-btn kr-btn--ghost kr-btn--compact"
                  type="button"
                  @click="cancelKeyEdit('rerank')"
                >
                  取消
                </button>
              </template>

              <template v-else-if="maskedOf('rerank')">
                <code class="key-badge">{{ maskedOf("rerank") }}</code>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('rerank')"
                >
                  替换
                </button>
                <button
                  class="kr-btn kr-btn--outline-danger kr-btn--compact"
                  type="button"
                  @click="startClear('rerank')"
                >
                  清除
                </button>
              </template>

              <template v-else>
                <span class="key-badge key-badge--empty">未配置</span>
                <button
                  class="kr-btn kr-btn--outline-primary kr-btn--compact"
                  type="button"
                  @click="startReplace('rerank')"
                >
                  填写
                </button>
              </template>
            </div>

            <span class="key-bar__sep" aria-hidden="true"></span>

            <div class="key-bar__right">
              <TestConnectionButton
                test-type="rerank"
                :provider="draft.rerankProvider"
                :model="draft.rerankModel"
                :base-url="draft.rerankBaseUrl"
                :api-key="replacingKey.rerank ? draft.rerankApiKey : ''"
                :has-saved-key="hasSavedKey('rerank')"
                :key-cleared="clearingKey.rerank"
              />
            </div>
          </div>
        </div>
      </section>

      <!-- ============ 操作区 ============ -->
      <div class="actions">
        <button class="kr-btn kr-btn--primary" type="button" :disabled="configStore.saving || !hasChanges" @click="handleSave">
          {{ configStore.saving ? "保存中…" : hasChanges ? "保存配置" : "没有改动" }}
        </button>
        <p class="actions__hint">
          API Key 加密存储，接口只返回脱敏值（如 <code>sk-****abcd</code>），不会回显明文。
        </p>
      </div>

      <p v-if="formError" class="alert alert--error" role="alert">{{ formError }}</p>
      <p v-else-if="successMessage" class="alert alert--success" role="status">{{ successMessage }}</p>

      <p v-if="configStore.lastIndexStale" class="alert alert--warning" role="status">
        检测到 Embedding 配置变化，已保存的向量索引需要重建后才能用于问答（索引功能将在 Phase 3 提供）。
        <button class="link" type="button" @click="configStore.dismissIndexStale()">知道了</button>
      </p>
    </template>

    <p v-else class="state state--error">
      {{ configStore.errorMessage ?? "无法加载配置，请稍后重试" }}
    </p>
  </div>
</template>

<style scoped>
.form-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

.section {
  padding: var(--kr-space-5);
}

.section__head {
  margin-bottom: var(--kr-space-4);
}

.section__title {
  font-size: 15px;
}

.section__desc {
  margin-top: 2px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

/* --- 表单栅格：Provider 与「模型名」两列并排，Base URL 占满整行 ---
   三个卡片共用同一套栅格，卡片 padding 与圆角都来自全局 .kr-panel（见 .section）。
   用 minmax(0, 1fr) 而不是 1fr：栅格子项默认 min-width: auto，遇到
   `Qwen/Qwen3-Reranker-...` 这类长模型名时会把列撑破，minmax(0, ·) 才压得住。 */
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  /* 列间距 16px（--kr-space-4）；行间距 20px 取自 UI_DESIGN_PROMPT
     「表单里标签与输入框间距 8px、表单项之间 20px」。
     20px 不在 --kr-space-* 的刻度里（4/8/12/16/24/32/48），因此这里写死并说明出处，
     而不是就近取 24px——"看起来差不多"会让文档与实现悄悄分叉。 */
  column-gap: var(--kr-space-4);
  row-gap: 20px;
}

/* 窄屏：两列压成一列。900px 是 UI_DESIGN_PROMPT 给出的断点 */
@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

/* Base URL 占满整行：它是卡片里唯一的"整行字段"，另外三处（Provider / 模型名 /
   采样参数）都是两列。 */
.field--wide {
  grid-column: 1 / -1;
}

/* --- 下拉框 ---
   原生 select 的箭头由操作系统绘制：形状、颜色、与边框的距离都不受控，深浅主题下
   还会各自变成另一种灰。这里关掉原生外观、自己画一个线性箭头，让它与旁边的输入框
   长得一样（同一圆角、同一边框、同一高度）；其余外观全部来自全局 .kr-input。
   注意：**展开后的选项列表仍由操作系统绘制**、无法用 CSS 定制，
   要改那一部分只能换成自定义 listbox 组件（本项目的语言是原生控件 + token，暂不引入）。 */
.select {
  position: relative;
  display: block;
}

.select select {
  appearance: none;
  -webkit-appearance: none;
  cursor: pointer;
  /* 给右侧箭头留位，否则长标签会压到箭头下面 */
  padding-right: 32px;
}

.select__chevron {
  position: absolute;
  top: 50%;
  right: 10px;
  width: 15px;
  height: 15px;
  transform: translateY(-50%);
  /* 用 currentColor 跟随主题，所以不必为深色单独准备一份图标资源 */
  color: var(--kr-text-muted);
  /* 关键：箭头不能吃掉点击，否则点在箭头区域时下拉框不展开 */
  pointer-events: none;
}

/* --- Base URL 的显隐 ---
   只在 custom（自定义端点）时出现。只做淡入淡出、不做高度动画：网格行高变化会牵动
   整张卡重排，做成动画反而像在抖。切换 provider 时地址值由 onProviderChange
   同步重置为新 provider 的默认值（custom 则清空为必填待填），因此不会留下残留值。 */
.reveal-enter-active,
.reveal-leave-active {
  transition:
    opacity var(--kr-transition),
    transform var(--kr-transition);
}

.reveal-enter-from,
.reveal-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* --- 凭据操作栏：单行两端对齐 ---
   左：API Key 标签 + 当前值；右：行内操作 + 测试连接。
   三个分区共用这一套，差异只有 kind。 */
.credential {
  /* 与上方的参数栅格拉开距离：24px 起步，避免"参数与 Key 挤在一起" */
  margin-top: var(--kr-space-5);
  padding-top: var(--kr-space-4);
  /* 卡内分隔线：把「模型参数」与「凭据 + 测试」分成两组。
     它不违反"页头不要通栏条"那条规则——那一条针对的是页面级容器，
     这里是卡片内部的分组。 */
  border-top: 1px solid var(--kr-border);
}

.key-bar {
  display: flex;
  align-items: center;
  /* 两端对齐：左组贴左、右组贴右，竖线落在两者之间 */
  justify-content: space-between;
  /* 不给容器 gap：竖线的左右 24px 由它自己的 margin 决定，
     容器 gap 会与 margin 叠加成 36px，让"左右各留 24px"这句话对不上实际 */
  gap: 0;
  flex-wrap: wrap;
  /* 与按钮同高（32px）：四种状态下这条栏的高度完全一致，切换时不跳 */
  min-height: 32px;
  /* 允许整条栏在窄容器里收缩：没有它，展开的输入框会把卡片顶宽 */
  min-width: 0;
}

.key-bar__left {
  display: flex;
  align-items: center;
  /* 组内紧凑：8px（标签 / 胶囊 / 按钮之间） */
  gap: var(--kr-space-2);
  /* 极窄时让"输入框"整块换到下一行，而不是把标签与胶囊挤扁 */
  flex-wrap: wrap;
  row-gap: var(--kr-space-2);
  /* 允许替换态里的输入框收缩，否则会把这一行撑破 */
  min-width: 0;
}

/* API Key 标签**绝不允许被挤成两行**。
   flex 子项默认 min-width: auto 且可收缩，输入框一变宽就会把标签压成逐字换行
   （"API" / "Key"）。nowrap + flex-shrink: 0 从根上堵掉；
   空间不够时应由输入框换行让位（见 .key-bar__left 的 flex-wrap）。 */
.key-bar__label {
  white-space: nowrap;
  flex-shrink: 0;
}

/* 中间的分隔竖线。用独立的 span 而不是给右组加 border-left：
   容器是 space-between，右组的 border-left 会紧贴在"测试连接"左边，
   而不是落在两组中间。 */
.key-bar__sep {
  align-self: center;
  width: 1px;
  height: 20px;
  background: var(--kr-border);
  margin: 0 var(--kr-space-5);   /* 左右各 24px */
  /* 竖线是 1px 的装饰线，被压成 0 宽就会消失 */
  flex-shrink: 0;
}

.key-bar__right {
  display: flex;
  align-items: center;
  gap: var(--kr-space-2);
  flex-wrap: wrap;
}

/* Key 的当前值：浅色胶囊 + 等宽字体。
   用 monospace 是因为它是机器串（sk-****af6c），等宽能让不同长度的 Key 看起来"对齐"；
   长 Key 用 break-all 换行，避免撑破卡片。 */
/* 值的胶囊：**已保存与未配置共用同一个**，只有文字色与字体不同——
   否则同一个位置会出现"有背景的胶囊"和"裸文字"两种形态，正是上一版的问题。 */
.key-badge {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px;
  padding: 4px 10px;
  border-radius: var(--kr-radius-sm);
  /* 用 token 而不是写死 rgba(0,0,0,0.04)：深色主题下黑色蒙层几乎不可见，
     胶囊会退化成"裸文字"，两个状态又变得不一样。
     --kr-muted-bg 在浅色下是 rgba(20,24,35,0.05)（与 0.04 视觉等价），
     深色下自动换成 rgba(255,255,255,0.07)。 */
  background: var(--kr-muted-bg);
  color: var(--kr-text);
  word-break: break-all;
  /* 胶囊不被压扁：空间不够时整块换行（父级 flex-wrap），而不是把里面的字挤散 */
  flex-shrink: 0;
  max-width: 100%;
}

/* 未配置：同一个胶囊、次要文字色、不用等宽字体（它不是机器串） */
.key-badge--empty {
  color: var(--kr-text-secondary);
  font-family: inherit;
}

/* 已标记为清除：同一个胶囊、警告色 */
.key-badge--warning {
  color: var(--kr-warning);
  font-family: inherit;
}

/* Key 输入框：只在「替换」态出现。占据标签与按钮之外的剩余空间（flex: 1），
   但保底 200px——否则在窄容器里它会一路收缩到几乎看不见。
   纵向 padding 归零 + min-height 32px：与同排按钮等高，切换状态时整条栏不跳。 */
.key-input {
  flex: 1;
  min-width: 200px;
  min-height: 32px;
  padding-block: 0;
}

/* 窄屏（≤900px，与上方栅格同一断点）：允许折行。
   折行后竖线不再有意义（两组已分处两行），因此隐藏；
   右组整组占满一行并贴右，保证折行后两边依然整齐。 */
@media (max-width: 900px) {
  .key-bar {
    align-items: flex-start;
    row-gap: var(--kr-space-3);
  }

  .key-bar__sep {
    display: none;
  }

  .key-bar__right {
    width: 100%;
    justify-content: flex-end;
  }
}

/* --- 文字链接 ---
   现在只剩提示条里的「知道了」这类纯文字操作（行内的替换/清除/填写已改为小按钮）。
   默认次要文字色（#6B7280 = --kr-text-secondary），hover 变主色。 */
.link {
  font: inherit;
  font-size: 12.5px;
  padding: 0;
  border: none;
  background: none;
  color: var(--kr-text-secondary);
  cursor: pointer;
  transition: color var(--kr-transition);
}

.link:hover {
  color: var(--kr-primary);
}

/* --- 操作区 ---
   保存按钮用全局 .kr-btn / .kr-btn--primary（高 36px、圆角 8px、字号 13px），
   不再在这里重写一套按钮样式：控件的尺寸与圆角必须只有一个来源，否则
   "设置页的按钮比别处高 2px"这类偏差永远查不出来。 */
.actions {
  display: flex;
  align-items: center;
  gap: var(--kr-space-4);
  flex-wrap: wrap;
}

.actions__hint {
  font-size: 12px;
  color: var(--kr-text-muted);
}

.actions__hint code {
  font-size: 11.5px;
  padding: 1px 5px;
  border-radius: var(--kr-radius-sm);
  background: var(--kr-muted-bg);
}

/* --- 提示条 --- */
.alert {
  font-size: 13px;
  padding: 10px 14px;
  border-radius: var(--kr-radius);
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-3);
  flex-wrap: wrap;
  /* 长文案必须换行，否则窄屏会溢出容器 */
  word-break: break-word;
}

.alert--error {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}

.alert--success {
  color: var(--kr-success);
  background: var(--kr-success-soft);
}

.alert--warning {
  color: var(--kr-warning);
  background: var(--kr-warning-soft);
}

.state {
  font-size: 13px;
  color: var(--kr-text-secondary);
  padding: var(--kr-space-5);
  text-align: center;
}

.state--error {
  color: var(--kr-danger);
}
</style>
