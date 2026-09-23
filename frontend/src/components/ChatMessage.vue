<script setup lang="ts">
import { computed } from "vue";

import SourceList from "@/components/SourceList.vue";
import { renderMarkdown } from "@/utils/markdown";
import type { ChatMessage } from "@/types/chat";

/**
 * 单条消息。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`——「安静、清晰、轻盈、留白充足」；
 * 「用户消息靠右或以轻色块区分」「AI 消息以正文阅读体验为主，不要过度卡片化」。
 *
 * 呈现方式（参考 DeepSeek 网页版）：
 * - **用户消息**：右侧浅色气泡，靠色块与对齐方式区分；
 * - **AI 消息**：无头像、无气泡、无背景/边框/阴影，直接以正文排版在页面背景上，
 *   只靠**间距与对齐**与用户消息区分。
 *
 * 为什么 AI 消息不再加容器样式：正文一旦被框起来，视觉重心就从"读内容"变成了
 * "看卡片"，长回答尤其明显。去掉容器后，Markdown 的标题/列表/代码块本身就成了
 * 唯一的层次来源，这也是设计规范里"不要过度卡片化"的字面要求。
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
    <div class="message__body">
      <!-- 用户消息：纯文本插值，天然免疫 XSS -->
      <p v-if="isUser" class="message__user-text">{{ message.content }}</p>

      <!-- AI 消息：已清洗的 Markdown HTML -->
      <template v-else>
        <!-- markdown--streaming 只用于让**最后一个块级子元素**通过 ::after 长出光标。
             光标不能作为兄弟节点放在这里：.markdown 是块级元素，紧随其后的行内元素
             会被挤到下一行，看起来像是"光标掉到了新的一行"。 -->
        <div
          v-if="message.content"
          class="markdown"
          :class="{ 'markdown--streaming': message.streaming }"
          v-html="renderedHtml"
        ></div>
        <p v-else-if="message.streaming" class="message__thinking">正在检索并生成回答…</p>

        <!-- 降级说明：开关开着但库是空的，这条回答没有依据知识库。
             这里保留极浅的背景色——它是**状态提示**而不是回答正文，
             不加任何底色会淹没在正文里、用户可能完全没看到。 -->
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
/* 说明：本文件里所有颜色都走 design token，而不是写死的十六进制。
   用户给出的取值与现有 token 一一对应（#18202F = --kr-text、#6B7280 =
   --kr-text-secondary、#9CA3AF = --kr-text-muted、rgba(79,125,255,.08) ≈
   --kr-primary-soft），因此用 token 在浅色下与规范完全一致，
   同时深色主题也能正确跟随——写死颜色会在深色下变成一片不可读。 */

.message {
  display: flex;
  min-width: 0;
}

/* 用户消息靠右；AI 消息已无头像，不需要 flex 布局 */
.message--user {
  justify-content: flex-end;
}

.message--ai {
  display: block;
}

.message__body {
  min-width: 0;
}

/* 用户气泡：右侧浅色块 */
.message--user .message__body {
  max-width: 78%;
}

.message__user-text {
  background: var(--kr-primary-soft);
  color: var(--kr-text);
  /* 圆角 12px（原为不对称的 18/8，改成统一 12px 更安静），内边距 12px 16px */
  padding: 12px 16px;
  border-radius: var(--kr-radius);
  white-space: pre-wrap;
  word-break: break-word;
}

/* AI 正文最大宽度 85%：大屏下限制每行字数，避免阅读时视线来回扫。
   更外层的 .messages 已有 760px 上限，这里是在此基础上再收一档。 */
.message--ai .message__body {
  max-width: 85%;
}

.message__thinking {
  font-size: 14px;
  color: var(--kr-text-muted);
}

.message__error {
  margin-top: var(--kr-space-3);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

/* 降级说明用警告色而不是错误色：回答本身是成功的，
   只是没有依据知识库，用错误色会让用户以为出错了。 */
.message__degraded {
  margin-top: var(--kr-space-3);
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--kr-warning);
  background: var(--kr-warning-soft);
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

/* trace_id：12px、次要灰、左对齐，与回答底部保持 8px 间距 */
.message__trace {
  margin-top: 8px;
  font-size: 12px;
  color: var(--kr-text-muted);
  word-break: break-all;
}

.message__trace code {
  font-size: 12px;
}

/* --- AI 正文：纯排版，无任何容器感 --- */
.markdown {
  font-size: 15px;
  line-height: 1.78;
  color: var(--kr-text);
  word-break: break-word;
  /* 刻意不设 background / border / box-shadow / border-radius / padding：
     AI 回答直接落在页面背景上，层次只由字号、行高与间距提供。 */
}

.markdown :deep(p) {
  margin: 0 0 14px;
}

.markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) {
  font-size: 16px;
  margin: 18px 0 10px;
}

.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 14px;
  padding-left: 22px;
}

.markdown :deep(li) {
  margin-bottom: 4px;
}

.markdown :deep(code) {
  font-family: var(--kr-font-mono);
  font-size: 13px;
  padding: 1px 5px;
  border-radius: var(--kr-radius-sm);
  background: var(--kr-code-bg);
}

/* 代码块只给极浅背景，不加边框——加了边框就又变成"卡片"了。
   横向滚动条常驻槽位的处理见 global.css 的 scrollbar-gutter。 */
.markdown :deep(pre) {
  margin: 0 0 14px;
  padding: var(--kr-space-3) var(--kr-space-4);
  border-radius: var(--kr-radius);
  background: var(--kr-code-bg);
  overflow-x: auto;
}

.markdown :deep(pre code) {
  padding: 0;
  background: none;
  font-size: 13px;
  line-height: 1.7;
}

.markdown :deep(blockquote) {
  margin: 0 0 14px;
  padding: 2px 0 2px 12px;
  border-left: 2px solid var(--kr-border-strong);
  color: var(--kr-text-secondary);
}

.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0 0 14px;
  font-size: 13.5px;
  width: 100%;
}

.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--kr-border);
  padding: 6px 10px;
  text-align: left;
}

.markdown :deep(th) {
  background: var(--kr-sunken);
  font-weight: 500;
}

.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--kr-border);
  margin: 16px 0;
}

.markdown :deep(a) {
  color: var(--kr-primary);
  text-decoration: underline;
}

/**
 * 流式光标。
 *
 * 用**最后一个块级子元素**的 `::after`，而不是在 .markdown 后面放一个兄弟节点：
 * 后者会被块级容器挤到下一行，看起来像"光标掉到了新的一行"。
 * 挂在最后一个子元素上，光标就紧跟在最后一个字符之后——
 * 无论结尾是段落、列表项还是标题都成立。
 */
.markdown--streaming :deep(> :last-child::after) {
  content: "";
  display: inline-block;
  width: 7px;
  height: 1em;
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

@media (prefers-reduced-motion: reduce) {
  .markdown--streaming :deep(> :last-child::after) {
    animation: none;
  }
}

/* 移动端：AI 正文占满可用宽度（窄屏下再留 15% 空白会挤得难读）。
   左右边距的收窄由 ChatView 的 .stream 内边距在 640px 断点处理。 */
@media (max-width: 640px) {
  .message--ai .message__body {
    max-width: 100%;
  }

  .message--user .message__body {
    max-width: 88%;
  }
}
</style>
