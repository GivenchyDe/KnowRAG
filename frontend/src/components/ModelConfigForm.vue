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
 * 两个关键交互约定：
 * 1. **API Key 不回显明文**。输入框留空表示「保持已保存的 Key 不变」；
 *    用户点「替换」后输入才会作为新 Key 提交；点「清除」会显式提交空字符串。
 *    这个三态（保持 / 替换 / 清除）与后端 `ModelConfigUpdate` 的语义严格对应。
 * 2. **只提交有改动的字段**。后端把「字段未提供」解释为「保持原值」，
 *    因此只发送改动项可以避免覆盖掉其他标签页或其他用户在期间做的修改。
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
  embedModel: "",
  rerankProvider: "",
  rerankApiKey: "",
  rerankModel: "",
});

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
  draft.embedModel = current.embed_model;

  draft.rerankProvider = current.rerank_provider;
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
}

onMounted(async () => {
  await Promise.all([configStore.load(), configStore.loadProviders()]);
  syncDraft();
});

/** 某类别的 provider 选项。取值一律来自后端目录，前端不硬编码 provider 与模型名。 */
function optionsFor(kind: "llm" | "embed" | "rerank"): ProviderOption[] {
  return providers.value?.[kind] ?? [];
}

/** 当前 provider 的目录项，用于取推荐模型与默认 base_url。 */
function currentOption(kind: "llm" | "embed" | "rerank", value: string): ProviderOption | undefined {
  return optionsFor(kind).find((option) => option.value === value);
}

/** 切换 provider 时把模型名与 base_url 换成该 provider 的默认值，避免内部不一致。 */
function onProviderChange(kind: "llm" | "embed" | "rerank"): void {
  const value = providerOf(kind);
  const option = currentOption(kind, value);
  if (!option) {
    return;
  }
  if (kind === "llm") {
    draft.llmModel = option.default_model;
    draft.llmBaseUrl = option.default_base_url ?? "";
  } else if (kind === "embed") {
    draft.embedModel = option.default_model;
  } else {
    draft.rerankModel = option.default_model;
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
  if (draft.embedModel !== current.embed_model) payload.embed_model = draft.embedModel;
  // 不提交 embed_dimension：向量维度由后端按模型实测值维护，见 types/config.ts 的说明。

  if (draft.rerankProvider !== current.rerank_provider) payload.rerank_provider = draft.rerankProvider;
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
          <p class="section__desc">用于生成回答，需填写你自己的 API Key</p>
        </header>

        <div class="grid">
          <label class="field">
            <span class="field__label">Provider</span>
            <span class="select">
              <select v-model="draft.llmProvider" class="field__control" @change="onProviderChange('llm')">
                <option v-for="option in optionsFor('llm')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="field">
            <span class="field__label">模型名</span>
            <input
              v-model="draft.llmModel"
              class="field__control"
              type="text"
              list="llm-models"
              placeholder="如 deepseek-chat"
            />
            <datalist id="llm-models">
              <option
                v-for="name in currentOption('llm', draft.llmProvider)?.suggested_models ?? []"
                :key="name"
                :value="name"
              />
            </datalist>
          </label>

          <label class="field field--wide">
            <span class="field__label">Base URL</span>
            <input
              v-model="draft.llmBaseUrl"
              class="field__control"
              type="text"
              placeholder="留空则使用官方地址"
            />
          </label>

          <label class="field">
            <span class="field__label">Temperature</span>
            <input
              v-model.number="draft.llmTemperature"
              class="field__control"
              type="number"
              min="0"
              max="2"
              step="0.1"
            />
            <span class="field__hint">知识库问答建议 0.1–0.3，保持稳定、少发散</span>
          </label>

          <label class="field">
            <span class="field__label">Max Tokens</span>
            <input
              v-model.number="draft.llmMaxTokens"
              class="field__control"
              type="number"
              min="1"
              max="131072"
              step="256"
            />
          </label>
        </div>

        <!-- 三类 provider 都是远程服务，都需要 API Key，因此这张表单只有一种形态 -->
        <div class="key-row">
          <span class="field__label">API Key</span>

          <template v-if="clearingKey.llm">
            <span class="key-pending">已标记为清除，保存后生效</span>
            <button class="link" type="button" @click="cancelKeyEdit('llm')">撤销</button>
          </template>

          <template v-else-if="replacingKey.llm">
            <input
              v-model="draft.llmApiKey"
              class="field__control field__control--key"
              type="password"
              autocomplete="off"
              placeholder="粘贴新的 API Key"
            />
            <button class="link" type="button" @click="cancelKeyEdit('llm')">取消</button>
          </template>

          <template v-else-if="maskedOf('llm')">
            <code class="key-masked">{{ maskedOf("llm") }}</code>
            <button class="link" type="button" @click="startReplace('llm')">替换</button>
            <button class="link link--danger" type="button" @click="startClear('llm')">清除</button>
          </template>

          <template v-else>
            <span class="key-empty">未配置</span>
            <button class="link" type="button" @click="startReplace('llm')">填写</button>
          </template>
        </div>

        <!-- 测试连接：三类模型共用同一个组件，交互与视觉完全一致 -->
        <TestConnectionButton
          test-type="llm"
          :provider="draft.llmProvider"
          :model="draft.llmModel"
          :base-url="draft.llmBaseUrl"
          :api-key="replacingKey.llm ? draft.llmApiKey : ''"
          :has-saved-key="hasSavedKey('llm')"
          :key-cleared="clearingKey.llm"
        />
      </section>

      <!-- ============ Embedding ============ -->
      <section class="kr-panel section">
        <header class="section__head">
          <h2 class="section__title">向量模型（Embedding）</h2>
          <p class="section__desc">决定文档与问题如何转成向量。修改这一组配置会使已有索引失效</p>
        </header>

        <div class="grid">
          <label class="field">
            <span class="field__label">Provider</span>
            <span class="select">
              <select v-model="draft.embedProvider" class="field__control" @change="onProviderChange('embed')">
                <option v-for="option in optionsFor('embed')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="field">
            <span class="field__label">模型名</span>
            <input
              v-model="draft.embedModel"
              class="field__control"
              type="text"
              list="embed-models"
            />
            <datalist id="embed-models">
              <option
                v-for="name in currentOption('embed', draft.embedProvider)?.suggested_models ?? []"
                :key="name"
                :value="name"
              />
            </datalist>
          </label>
        </div>

        <div class="key-row">
          <span class="field__label">API Key</span>
          <template v-if="clearingKey.embed">
            <span class="key-pending">已标记为清除，保存后生效</span>
            <button class="link" type="button" @click="cancelKeyEdit('embed')">撤销</button>
          </template>
          <template v-else-if="replacingKey.embed">
            <input
              v-model="draft.embedApiKey"
              class="field__control field__control--key"
              type="password"
              autocomplete="off"
              placeholder="粘贴新的 API Key"
            />
            <button class="link" type="button" @click="cancelKeyEdit('embed')">取消</button>
          </template>
          <template v-else-if="maskedOf('embed')">
            <code class="key-masked">{{ maskedOf("embed") }}</code>
            <button class="link" type="button" @click="startReplace('embed')">替换</button>
            <button class="link link--danger" type="button" @click="startClear('embed')">清除</button>
          </template>
          <template v-else>
            <span class="key-empty">未配置</span>
            <button class="link" type="button" @click="startReplace('embed')">填写</button>
          </template>
        </div>

        <TestConnectionButton
          test-type="embed"
          :provider="draft.embedProvider"
          :model="draft.embedModel"
          :api-key="replacingKey.embed ? draft.embedApiKey : ''"
          :has-saved-key="hasSavedKey('embed')"
          :key-cleared="clearingKey.embed"
        />
      </section>

      <!-- ============ Reranker ============ -->
      <section class="kr-panel section">
        <header class="section__head">
          <h2 class="section__title">重排模型（Reranker）</h2>
          <p class="section__desc">对检索候选重新排序，提高引用片段的相关性。修改它不需要重建索引</p>
        </header>

        <div class="grid">
          <label class="field">
            <span class="field__label">Provider</span>
            <span class="select">
              <select v-model="draft.rerankProvider" class="field__control" @change="onProviderChange('rerank')">
                <option v-for="option in optionsFor('rerank')" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <svg class="select__chevron" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 9.5l6 6 6-6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
          </label>

          <label class="field">
            <span class="field__label">模型名</span>
            <input
              v-model="draft.rerankModel"
              class="field__control"
              type="text"
              list="rerank-models"
            />
            <datalist id="rerank-models">
              <option
                v-for="name in currentOption('rerank', draft.rerankProvider)?.suggested_models ?? []"
                :key="name"
                :value="name"
              />
            </datalist>
          </label>
        </div>

        <div class="key-row">
          <span class="field__label">API Key</span>
          <template v-if="clearingKey.rerank">
            <span class="key-pending">已标记为清除，保存后生效</span>
            <button class="link" type="button" @click="cancelKeyEdit('rerank')">撤销</button>
          </template>
          <template v-else-if="replacingKey.rerank">
            <input
              v-model="draft.rerankApiKey"
              class="field__control field__control--key"
              type="password"
              autocomplete="off"
              placeholder="粘贴新的 API Key"
            />
            <button class="link" type="button" @click="cancelKeyEdit('rerank')">取消</button>
          </template>
          <template v-else-if="maskedOf('rerank')">
            <code class="key-masked">{{ maskedOf("rerank") }}</code>
            <button class="link" type="button" @click="startReplace('rerank')">替换</button>
            <button class="link link--danger" type="button" @click="startClear('rerank')">清除</button>
          </template>
          <template v-else>
            <span class="key-empty">未配置</span>
            <button class="link" type="button" @click="startReplace('rerank')">填写</button>
          </template>
        </div>

        <TestConnectionButton
          test-type="rerank"
          :provider="draft.rerankProvider"
          :model="draft.rerankModel"
          :api-key="replacingKey.rerank ? draft.rerankApiKey : ''"
          :has-saved-key="hasSavedKey('rerank')"
          :key-cleared="clearingKey.rerank"
        />
      </section>

      <!-- ============ 操作区 ============ -->
      <div class="actions">
        <button class="btn btn--primary" type="button" :disabled="configStore.saving || !hasChanges" @click="handleSave">
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

/* --- 字段栅格：窄屏自动降为单列，避免文本溢出 --- */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--kr-space-4);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
  min-width: 0;
}

.field--wide {
  grid-column: 1 / -1;
}

.field__label {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--kr-text);
}

.field__control {
  font: inherit;
  width: 100%;
  padding: 8px 12px;
  /* 输入框圆角取全局 token（10px），与弹窗里的输入框、历史页搜索框一致 */
  border-radius: var(--kr-radius-input);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  transition:
    border-color var(--kr-transition),
    box-shadow var(--kr-transition);
}

.field__control:hover:not(:focus) {
  border-color: var(--kr-input-border);
}

.field__control:focus {
  outline: none;
  border-color: var(--kr-primary);
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}

/* --- 下拉框 ---
   原生 select 的问题是那个由操作系统绘制的箭头：形状、颜色、与边框的距离都不受控，
   深浅主题下还会各自变成另一种灰。这里关掉原生外观、自己画一个线性箭头，
   让它与旁边的输入框长得一样（同一圆角、同一边框、同一高度）。
   注意：**展开后的选项列表仍由操作系统绘制、无法用 CSS 定制**，
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

.field__control--key {
  max-width: 320px;
}

.field__hint {
  font-size: 11.5px;
  color: var(--kr-text-muted);
  line-height: 1.6;
}

/* --- API Key 行 --- */
.key-row {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  flex-wrap: wrap;
  margin-top: var(--kr-space-4);
  padding-top: var(--kr-space-4);
  border-top: 1px solid var(--kr-border);
}

.key-row > .field__label {
  flex: none;
  min-width: 64px;
}

.key-masked {
  font-size: 12.5px;
  padding: 4px 10px;
  border-radius: var(--kr-radius-sm);
  background: var(--kr-muted-bg);
  word-break: break-all;
}

.key-empty {
  font-size: 12.5px;
  color: var(--kr-text-muted);
}

.key-pending {
  font-size: 12.5px;
  color: var(--kr-warning);
}

.link {
  font: inherit;
  font-size: 12.5px;
  padding: 0;
  border: none;
  background: none;
  color: var(--kr-primary);
  cursor: pointer;
}

.link:hover {
  text-decoration: underline;
}

.link--danger {
  color: var(--kr-danger);
}

/* --- 操作区 --- */
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

.btn {
  font: inherit;
  font-weight: 500;
  border-radius: var(--kr-radius);
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    opacity var(--kr-transition);
}

.btn--primary {
  padding: 10px 20px;
  color: var(--kr-on-primary);
  background: var(--kr-primary);
}

.btn--primary:hover:not(:disabled) {
  background: var(--kr-primary-hover);
}

.btn--primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn--ghost {
  padding: 6px 14px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  background: transparent;
  border-color: var(--kr-border-strong);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.btn--ghost:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
