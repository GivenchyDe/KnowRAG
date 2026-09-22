<script setup lang="ts">
import { computed } from "vue";

import SourceList from "@/components/SourceList.vue";
import { renderMarkdown } from "@/utils/markdown";
import type { ChatMessage } from "@/types/chat";

/**
 * 消息气泡。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`——用户消息靠右或用轻色块区分；
 * AI 消息以正文阅读体验为主，不要过度卡片化。
 * 因此用户消息用浅色块 + 右对齐，AI 消息不加边框，直接以正文呈现。
 *
 * 安全边界：AI 回答经 `renderMarkdown` 处理（markdown-it 禁 HTML +
 * 协议白名单 + DOMPurify 清洗），结果通过 `v-html` 插入是安全的。
 * 用户消息一律用 `{{ }}` 文本插值，不走 HTML 渲染。
 */

const props = defineProps<{ message: ChatMessage }>();

const renderedHtml = computed(() => renderMarkdown(props.message.content));
const isUser = computed(() => props.message.role === "user");
</script>

<template>
  <div class="message" :class="isUser ? 'message--user' : 'message--ai'">
    <div v-if="!isUser" class="message__avatar" aria-hidden="true">AI</div>

    <div class="message__body">
      <!-- 用户消息：纯文本插值，天然免疫 XSS -->
      <p v-if="isUser" class="message__user-text">{{ message.content }}</p>

      <!-- AI 消息：已清洗的 Markdown HTML -->
      <template v-else>
        <div v-if="message.content" class="markdown" v-html="renderedHtml"></div>
        <p v-else-if="message.streaming" class="message__thinking">正在检索并生成回答…</p>

        <!-- 流式光标：让用户明确知道还在输出 -->
        <span v-if="message.streaming && message.content" class="cursor" aria-hidden="true"></span>

        <!-- 降级说明：开关开着但库是空的，这条回答没有依据知识库 -->
        <p v-if="message.degraded" class="message__degraded" role="status">
          知识库为空，已按普通对话回答。上传文档后可开启知识库问答。
        </p>

        <p v-if="message.error" class="message__error" role="alert">
          {{ message.error }}
        </p>

        <SourceList :sources="message.sources" />

        <p v-if="message.traceId" class="message__trace">
          trace_id: <code>{{ message.traceId }}</code>
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  gap: var(--kr-space-3);
  min-width: 0;
}

.message--user {
  justify-content: flex-end;
}

.message__avatar {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-size: 10.5px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-top: 2px;
}

.message__body {
  min-width: 0;
  max-width: 100%;
}

.message--user .message__body {
  max-width: 78%;
}

/* 用户消息：浅色块 + 右对齐 */
.message__user-text {
  background: var(--kr-primary-soft);
  color: var(--kr-text);
  padding: 9px 14px;
  border-radius: var(--kr-radius-lg) var(--kr-radius-lg) var(--kr-radius-sm) var(--kr-radius-lg);
  white-space: pre-wrap;
  word-break: break-word;
}

.message--ai .message__body {
  flex: 1;
}

.message__thinking {
  font-size: 13px;
  color: var(--kr-text-muted);
}

.message__error {
  margin-top: var(--kr-space-2);
  font-size: 12.5px;
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

/* 降级说明用警告色而不是错误色：回答本身是成功的，
   只是没有依据知识库，用错误色会让用户以为出错了。 */
.message__degraded {
  margin-top: var(--kr-space-2);
  font-size: 12.5px;
  color: var(--kr-warning);
  background: var(--kr-warning-soft);
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

.message__trace {
  margin-top: var(--kr-space-2);
  font-size: 11px;
  color: var(--kr-text-muted);
  word-break: break-all;
}

.message__trace code {
  font-size: 10.5px;
}

/* 流式光标 */
.cursor {
  display: inline-block;
  width: 7px;
  height: 14px;
  margin-left: 2px;
  background: var(--kr-primary);
  vertical-align: text-bottom;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  0%,
  50% {
    opacity: 1;
  }
  50.01%,
  100% {
    opacity: 0;
  }
}

/* --- Markdown 正文样式：追求阅读体验，不做卡片化 --- */
.markdown {
  font-size: 14px;
  line-height: 1.75;
  color: var(--kr-text);
  word-break: break-word;
}

.markdown :deep(p) {
  margin: 0 0 10px;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-size: 15px;
  margin: 16px 0 8px;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 10px;
  padding-left: 22px;
}

.markdown :deep(li) {
  margin-bottom: 3px;
}

.markdown :deep(code) {
  font-family: var(--kr-font-mono);
  font-size: 12.5px;
  padding: 1px 5px;
  border-radius: var(--kr-radius-sm);
  background: rgba(20, 24, 35, 0.06);
}

.markdown :deep(pre) {
  margin: 0 0 10px;
  padding: var(--kr-space-3) var(--kr-space-4);
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  background: rgba(20, 24, 35, 0.04);
  overflow-x: auto;
}

.markdown :deep(pre code) {
  padding: 0;
  background: none;
  font-size: 12.5px;
  line-height: 1.7;
}

.markdown :deep(blockquote) {
  margin: 0 0 10px;
  padding: 2px 0 2px 12px;
  border-left: 2px solid var(--kr-border-strong);
  color: var(--kr-text-secondary);
}

.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0 0 10px;
  font-size: 13px;
  width: 100%;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--kr-border);
  padding: 5px 9px;
  text-align: left;
}

.markdown :deep(th) {
  background: rgba(20, 24, 35, 0.03);
  font-weight: 500;
}

.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--kr-border);
  margin: 14px 0;
}

.markdown :deep(a) {
  color: var(--kr-primary);
  text-decoration: underline;
}

@media (max-width: 640px) {
  .message--user .message__body {
    max-width: 88%;
  }
}
</style>
