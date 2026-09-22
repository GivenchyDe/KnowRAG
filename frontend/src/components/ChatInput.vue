<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";

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
  /** 知识库是否就绪（后端判定索引可用），未就绪时给出提示但仍允许关闭开关后纯对话 */
  indexReady: boolean;
  /** 知识库中已索引的文档数。为 0 表示库里确实没有内容 */
  documentCount: number;
}>();

const emit = defineEmits<{
  send: [text: string];
  stop: [];
  "update:knowledgeEnabled": [value: boolean];
}>();

const text = ref("");

/**
 * 知识库为空。
 *
 * 与「索引未就绪」是两件事，必须分开判断：
 * - 空（documentCount === 0）：库里根本没内容，开了知识库必然什么都答不出来，
 *   因此**禁用输入**并引导去上传文档；
 * - 未就绪（有文档但索引没建好/已过期）：内容存在，只是还没索引，
 *   此时不禁用输入，提示去重建索引即可。
 *
 * 之前只判断了「未就绪」并显示一行警告，用户仍然可以发送，
 * 结果必然得到一句「没找到相关资料」——把可用性问题伪装成了检索问题。
 */
const knowledgeEmpty = computed(() => props.documentCount === 0);

/** 开启了知识库但库是空的：这是唯一需要禁用输入的场景。 */
const blockedByEmptyKnowledge = computed(() => props.knowledgeEnabled && knowledgeEmpty.value);

const canSend = computed(
  () => text.value.trim().length > 0 && !props.streaming && !blockedByEmptyKnowledge.value,
);

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
    <!-- 知识库为空时的引导。位置在输入框上方，符合「先看到原因再看到输入框」的阅读顺序 -->
    <div v-if="blockedByEmptyKnowledge" class="composer__guide" role="status">
      <span class="composer__guide-mark" aria-hidden="true">!</span>
      <div class="composer__guide-text">
        <p class="composer__guide-title">知识库为空，请先上传文档后再开启知识库问答</p>
        <p class="composer__guide-hint">
          当前知识库中没有任何已索引的文档，继续提问必然检索不到内容。
          可以先去
          <RouterLink to="/documents">文档管理</RouterLink>
          上传文档；或关闭下方的「知识库」开关，直接进行普通对话。
        </p>
      </div>
    </div>

    <div class="composer__box" :class="{ 'composer__box--blocked': blockedByEmptyKnowledge }">
      <textarea
        v-model="text"
        class="composer__input"
        rows="2"
        :placeholder="
          blockedByEmptyKnowledge
            ? '知识库为空，请先上传文档，或关闭「知识库」开关'
            : '输入问题，Enter 发送，Shift+Enter 换行'
        "
        :disabled="streaming || blockedByEmptyKnowledge"
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
          :disabled="streaming || blockedByEmptyKnowledge"
          @change="toggleKnowledge"
        />
        <span class="toggle__track" aria-hidden="true"><span class="toggle__thumb"></span></span>
        <span class="toggle__label">知识库</span>
      </label>

      <span class="composer__model" :title="modelLabel">{{ modelLabel }}</span>

      <span v-if="knowledgeEnabled && knowledgeEmpty" class="composer__warn">
        知识库为空，无法开启知识库问答
      </span>
      <span v-else-if="knowledgeEnabled && !indexReady" class="composer__warn">
        索引未就绪，发送后会提示需要先建立索引
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

/* 知识库为空被禁用时：输入框视觉上明确「不可用」，
   而不是看起来正常却点不动。 */
.composer__box--blocked {
  background: rgba(20, 24, 35, 0.03);
  border-style: dashed;
}

/* --- 知识库为空的引导条 --- */
.composer__guide {
  display: flex;
  align-items: flex-start;
  gap: var(--kr-space-3);
  width: 100%;
  margin-bottom: var(--kr-space-3);
  padding: var(--kr-space-3) var(--kr-space-4);
  border-radius: var(--kr-radius);
  border: 1px solid rgba(217, 119, 6, 0.28);
  background: var(--kr-warning-soft);
  color: var(--kr-warning);
  /* 长文案必须换行，否则窄屏会溢出容器 */
  word-break: break-word;
}

.composer__guide-mark {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--kr-warning);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.composer__guide-text {
  min-width: 0;
}

.composer__guide-title {
  font-size: 13px;
  font-weight: 500;
}

.composer__guide-hint {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--kr-text-secondary);
}

.composer__guide-hint a {
  color: var(--kr-primary);
  text-decoration: underline;
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
