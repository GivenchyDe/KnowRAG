<script setup lang="ts">
import { computed, ref } from "vue";

import { useConfigStore } from "@/stores/config";
import { useUiStore } from "@/stores/ui";
import { toErrorMessage } from "@/types/errors";
import type { ConnectionTestKind, ConnectionTestResult } from "@/types/config";

/**
 * 「测试连接」按钮（LLM / Embedding / Reranker 共用）。
 *
 * 抽成组件的理由：三类模型的测试交互完全一致（用已保存的 Key 还是临时输入的 Key、
 * 加载态、成功/失败提示、按钮旁的小字），只有"测什么"不同。写在三个区域里必然出现
 * 三份会各自漂移的副本——之前只有 LLM 有测试按钮，正是因为复制成本高才没做另外两个。
 *
 * 取 Key 的优先级（与后端 `use_saved_key` 的语义一一对应）：
 * 1. 用户临时输入了新 Key → 用它，`use_saved_key: false`；
 * 2. 否则若已保存过 Key → `use_saved_key: true`，**不传** api_key / base_url / model
 *    （后端在使用已保存的 Key 时只信数据库里的地址，传了也会被忽略，
 *    传了反而让人以为"测的是我刚改的地址"）；
 * 3. 两者都没有 → 不发请求，直接提示（所有 provider 都是远程服务，没有 Key 无法测试）。
 *
 * 不用已保存的 Key 时会把表单里填的 Base URL 一起传过去：后端在这条分支上允许
 * 调用方指定地址（"先测再存"），而只传 Key 不传地址会测到目录里的默认地址，
 * 用户填的自定义地址等于没测。
 *
 * 本组件不持有任何 Key 状态：apiKey 由父组件传入（表单草稿），测试完成后也不缓存。
 */
const props = withDefaults(
  defineProps<{
    /** 当前 provider 取值，如 `deepseek` / `qwen`（由后端目录提供，前端不硬编码） */
    provider: string;
    /** 模型名 */
    model: string;
    /** 测试类别。取值与后端 `kind` 一致（llm / embed / rerank），避免多一层映射表 */
    testType: ConnectionTestKind;
    /** 表单里填的 Base URL（仅 LLM 有意义）。留空时后端按 provider 目录兜底 */
    baseUrl?: string;
    /** 用户临时输入的新 Key；为空表示"没有新 Key" */
    apiKey?: string;
    /** 是否已保存过该模型的 Key（决定能否走"已保存的 Key"这条路） */
    hasSavedKey: boolean;
    /**
     * 是否主动放弃使用已保存的 Key（用户点了「清除」但还没保存）。
     * 单独一个 prop 而不是把 hasSavedKey 传 false：那样父组件的语义会变成
     * "清除后就没保存过"，与后端状态不符，别的判断也会跟着错。
     */
    keyCleared?: boolean;
  }>(),
  { baseUrl: "", apiKey: "", keyCleared: false },
);

const emit = defineEmits<{
  success: [result: ConnectionTestResult];
  error: [error: unknown];
}>();

const configStore = useConfigStore();
const ui = useUiStore();
const testing = ref(false);

/** 本次是否会使用已保存的 Key（用于按钮旁的小字提示）。 */
const willUseSavedKey = computed(
  () => !props.apiKey.trim() && props.hasSavedKey && !props.keyCleared,
);

/** 成功提示按类别区分：只说"连接成功"用户不知道测通了哪一环。 */
const SUCCESS_MESSAGE: Record<ConnectionTestKind, string> = {
  llm: "对话模型连接成功，模型响应正常",
  embed: "向量模型连接成功，模型返回正常向量",
  rerank: "重排模型连接成功，重排响应正常",
};

/**
 * 成功提示的补充说明。
 *
 * Embedding 的向量维度由**后端按实测值维护**（界面上已没有输入框），
 * 所以"维度被自动改了"这件事必须由界面讲出来——否则用户看到维度变了却不知道是谁改的，
 * 也不知道要不要重建索引。后端在 `detail` 里给出机器可读的标记，文案由前端组织。
 */
function successNote(result: ConnectionTestResult): string {
  const detail = result.detail ?? {};
  const dimension = detail["dimension"];
  if (props.testType !== "embed" || typeof dimension !== "number") {
    return "";
  }
  if (detail["dimension_synced"] !== true) {
    return `（实测 ${dimension} 维）`;
  }
  const stale = detail["stale_indexes"];
  const rebuild = typeof stale === "number" && stale > 0 ? "，已有索引需要重建" : "";
  return `（实测 ${dimension} 维，已自动更新配置中的向量维度${rebuild}）`;
}

async function handleTest(): Promise<void> {
  const typedKey = props.apiKey.trim();
  const useSavedKey = !typedKey && props.hasSavedKey && !props.keyCleared;

  if (!useSavedKey && !typedKey) {
    // 请求发出去也只会得到 400/422，不如在前端就给出可操作的一句话。
    ui.toast("请先填写并保存 API Key，或临时输入一个 Key 进行测试", "warning");
    return;
  }

  testing.value = true;
  try {
    const result = await configStore.testConnection({
      kind: props.testType,
      provider: props.provider,
      // 用已保存的 Key 时**不带** api_key / base_url / model，见文件头说明。
      ...(useSavedKey
        ? { use_saved_key: true }
        : {
            use_saved_key: false,
            api_key: typedKey,
            base_url: props.baseUrl.trim() || undefined,
            model: props.model,
          }),
    });

    if (result.success) {
      // 后端返回的 message 也不错（"模型返回 1024 维向量"），但界面文案要带上
      // "是哪个模型测通了"，因此成功走本组件的文案（+ 维度补充说明），
      // 失败才用后端的具体原因。
      ui.toast(SUCCESS_MESSAGE[props.testType] + successNote(result), "success");
      emit("success", result);
    } else {
      // 后端已把供应商原始报文转成可操作提示（"API Key 无效或没有访问权限"等），
      // 直接展示它，不要再套一层"测试失败"。
      ui.toast(result.message, "warning");
      emit("error", result);
    }
  } catch (error) {
    // 网络层/鉴权层的失败：错误对象里有可读文案（api/client.ts 已统一转换）
    ui.toast(toErrorMessage(error), "warning");
    emit("error", error);
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <div class="test-connection">
    <button class="btn btn--ghost" type="button" :disabled="testing" @click="handleTest">
      {{ testing ? "测试中…" : "测试连接" }}
    </button>
    <!-- 说明这次点下去用的是哪把 Key：用户看不到明文，必须由界面告诉他"测的是已保存的那把" -->
    <span v-if="willUseSavedKey" class="test-connection__hint">使用已保存的 Key 测试</span>
  </div>
</template>

<style scoped>
.test-connection {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  flex-wrap: wrap;
}

/* 按钮样式与其他次要按钮一致（圆角 10px / 高 36px 由全局 .kr-btn 体系提供，
   这里沿用页面已有的 .btn 类，保证三处按钮视觉完全相同） */
.btn {
  font: inherit;
  font-weight: 500;
  min-height: 36px;
  line-height: 1.2;
  font-size: 13px;
  padding: 8px 16px;
  border-radius: var(--kr-radius-btn);
  cursor: pointer;
  transition:
    background var(--kr-transition),
    border-color var(--kr-transition),
    color var(--kr-transition);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn--ghost {
  border: 1px solid var(--kr-border-strong);
  background: transparent;
  color: var(--kr-text-secondary);
}

.btn--ghost:hover:not(:disabled) {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.test-connection__hint {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}
</style>
