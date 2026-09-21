<script setup lang="ts">
import { computed, ref } from "vue";

/**
 * 底部输入区。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`——固定在主区底部、大圆角输入框、支持多行输入、
 * 发送按钮使用图标、附近展示当前模型与知识库开关。
 *
 * 交互约定：
 * - Enter 发送，Shift+Enter 换行（聊天界面的通用预期）；
 * - 生成中时发送按钮变为「停止」，而不是仅禁用——
 *   否则用户想中断一个跑偏的回答时无从下手。
 */

const props = defineProps<{
  /** 是否正在生成 */
  streaming: boolean;
  /** 知识库开关状态 */
  knowledgeEnabled: boolean;
  /** 当前模型名，用于展示 */
  modelLabel: string;
  /** 知识库是否就绪，未就绪时给出提示但仍允许关闭开关后纯对话 */
  indexReady: boolean;
}>();

const emit = defineEmits<{
  send: [text: string];
  stop: [];
  "update:knowledgeEnabled": [value: boolean];
}>();

const text = ref("");

const canSend = computed(() => text.value.trim().length > 0 && !props.streaming);

function handleSend(): void {
  if (!canSend.value) {
    return;
  }
  emit("send", text.value);
  text.value = "";
}

/** Enter 发送、Shift+Enter 换行。输入法组合期间不响应 Enter。 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key !== "Enter" || event.shiftKey) {
    return;
  }
  // isComposing 为 true 表示正在用中文输入法选词，此时 Enter 是「确认候选词」，
  // 不拦掉的话用户每选一次词就会误发一条消息。
  if (event.isComposing) {
    return;
  }
  event.preventDefault();
  handleSend();
}

function toggleKnowledge(): void {
  emit("update:knowledgeEnabled", !props.knowledgeEnabled);
}
</script>

<template>
  <footer class="composer">
    <div class="composer__box">
      <textarea
        v-model="text"
        class="composer__input"
        rows="2"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        :disabled="streaming"
        @keydown="handleKeydown"
      ></textarea>

      <button
        v-if="streaming"
        class="composer__btn composer__btn--stop"
        type="button"
        aria-label="停止生成"
        @click="emit('stop')"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
      </button>
      <button
        v-else
        class="composer__btn"
        type="button"
        :disabled="!canSend"
        aria-label="发送"
        @click="handleSend"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 12h15M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
    </div>

    <div class="composer__meta">
      <label class="toggle">
        <input
          type="checkbox"
          :checked="knowledgeEnabled"
          :disabled="streaming"
          @change="toggleKnowledge"
        />
        <span class="toggle__track" aria-hidden="true"><span class="toggle__thumb"></span></span>
        <span class="toggle__label">知识库</span>
      </label>

      <span class="composer__model" :title="modelLabel">{{ modelLabel }}</span>

      <span v-if="knowledgeEnabled && !indexReady" class="composer__warn">
        知识库未就绪，发送后会提示需要先建立索引
      </span>
    </div>
  </footer>
</template>

<style scoped>
.composer {
  padding: var(--kr-space-4) var(--kr-space-5) var(--kr-space-5);
  border-top: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.composer__box {
  display: flex;
  align-items: flex-end;
  gap: var(--kr-space-3);
  width: 100%;
  padding: var(--kr-space-3);
  border-radius: var(--kr-radius-lg);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  transition:
    border-color var(--kr-transition),
    box-shadow var(--kr-transition);
}

.composer__box:focus-within {
  border-color: var(--kr-primary);
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}

.composer__input {
  font: inherit;
  flex: 1;
  min-width: 0;
  border: none;
  resize: none;
  background: transparent;
  color: var(--kr-text);
  line-height: 1.6;
}

.composer__input::placeholder {
  color: var(--kr-text-muted);
}

.composer__input:focus {
  outline: none;
}

.composer__input:disabled {
  color: var(--kr-text-muted);
  cursor: not-allowed;
}

.composer__btn {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: var(--kr-primary);
  cursor: pointer;
  transition:
    background var(--kr-transition),
    opacity var(--kr-transition);
}

.composer__btn:hover:not(:disabled) {
  background: #3f6ce0;
}

.composer__btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.composer__btn--stop {
  background: var(--kr-text-secondary);
}

.composer__btn--stop:hover {
  background: var(--kr-text);
}

.composer__meta {
  display: flex;
  align-items: center;
  gap: var(--kr-space-4);
  flex-wrap: wrap;
  margin-top: var(--kr-space-3);
  font-size: 11.5px;
  color: var(--kr-text-muted);
}

.composer__model {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.composer__warn {
  color: var(--kr-warning);
}

/* --- 开关 --- */
.toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--kr-space-2);
  cursor: pointer;
  user-select: none;
}

.toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle__track {
  width: 30px;
  height: 17px;
  border-radius: var(--kr-radius-pill);
  background: rgba(20, 24, 35, 0.15);
  position: relative;
  transition: background var(--kr-transition);
  flex: none;
}

.toggle__thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: #fff;
  transition: transform var(--kr-transition);
  box-shadow: var(--kr-shadow-sm);
}

.toggle input:checked + .toggle__track {
  background: var(--kr-primary);
}

.toggle input:checked + .toggle__track .toggle__thumb {
  transform: translateX(13px);
}

.toggle input:focus-visible + .toggle__track {
  outline: 2px solid var(--kr-primary);
  outline-offset: 2px;
}

.toggle input:disabled + .toggle__track {
  opacity: 0.5;
}

.toggle__label {
  color: var(--kr-text-secondary);
}

@media (max-width: 640px) {
  .composer {
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .composer__model {
    max-width: 140px;
  }
}
</style>
