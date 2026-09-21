import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as configApi from "@/api/config";
import { useAuthStore } from "@/stores/auth";
import { toErrorMessage } from "@/types/errors";
import type {
  ConnectionTestRequest,
  ConnectionTestResult,
  ModelConfig,
  ModelConfigUpdate,
  ModelConfigUpdateResult,
  ProvidersResponse,
} from "@/types/config";

/**
 * 全局模型配置状态。
 *
 * 与 authStore 的关系：本 store 依赖 authStore 提供 token，反之不成立。
 * 这是单向依赖，不会形成循环。
 */
export const useConfigStore = defineStore("config", () => {
  const auth = useAuthStore();

  const config = ref<ModelConfig | null>(null);
  const providers = ref<ProvidersResponse | null>(null);
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref<string | null>(null);
  /** 最近一次保存是否导致索引失效，用于设置页的提示条 */
  const lastIndexStale = ref(false);

  /** 是否已配置 LLM 的 API Key。问答功能依赖它，ChatView 会用到。 */
  const llmKeyConfigured = computed(() => config.value?.llm_api_key_masked !== null);

  async function load(force = false): Promise<void> {
    if (config.value && !force) {
      return;
    }
    loading.value = true;
    errorMessage.value = null;
    try {
      config.value = await configApi.fetchModelConfig(auth.accessToken);
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      throw error;
    } finally {
      loading.value = false;
    }
  }

  /**
   * 加载 provider 目录。
   *
   * 目录只是下拉选项，加载失败不应挡住整个设置页（用户仍能看到并保存已有配置），
   * 因此这里吞掉异常、只记录错误文案。
   */
  async function loadProviders(): Promise<void> {
    if (providers.value) {
      return;
    }
    try {
      providers.value = await configApi.fetchProviders(auth.accessToken);
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
    }
  }

  async function save(payload: ModelConfigUpdate): Promise<ModelConfigUpdateResult> {
    saving.value = true;
    errorMessage.value = null;
    try {
      const result = await configApi.updateModelConfig(payload, auth.accessToken);
      lastIndexStale.value = result.index_stale;
      // 保存后重新拉取：后端会补齐「切换 provider 时的默认模型名 / base_url」，
      // 不回读的话表单里显示的仍是用户输入的旧值，与实际生效配置不一致。
      config.value = await configApi.fetchModelConfig(auth.accessToken);
      return result;
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      throw error;
    } finally {
      saving.value = false;
    }
  }

  async function testConnection(payload: ConnectionTestRequest): Promise<ConnectionTestResult> {
    return configApi.testConnection(payload, auth.accessToken);
  }

  function clearError(): void {
    errorMessage.value = null;
  }

  function dismissIndexStale(): void {
    lastIndexStale.value = false;
  }

  return {
    config,
    providers,
    loading,
    saving,
    errorMessage,
    lastIndexStale,
    llmKeyConfigured,
    load,
    loadProviders,
    save,
    testConnection,
    clearError,
    dismissIndexStale,
  };
});
