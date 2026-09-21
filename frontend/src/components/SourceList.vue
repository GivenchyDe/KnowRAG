<script setup lang="ts">
import type { SourceItem } from "@/types/chat";

/**
 * 引用来源列表。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 要求 AI 回答底部展示引用来源。
 * 编号与 Prompt 里的 `[1] [2]` 对应，用户据此可以核对回答依据。
 */

defineProps<{
  sources: SourceItem[];
  /** 紧凑模式用于右侧信息面板，默认模式用于回答气泡下方 */
  compact?: boolean;
}>();
</script>

<template>
  <div v-if="sources.length > 0" class="sources" :class="{ 'sources--compact': compact }">
    <p class="sources__title">引用来源（{{ sources.length }}）</p>
    <ol class="sources__list">
      <li v-for="(source, index) in sources" :key="source.chunk_id" class="source">
        <span class="source__index">{{ index + 1 }}</span>
        <div class="source__body">
          <span class="source__name">{{ source.filename }}</span>
          <span class="source__meta">
            <code>{{ source.chunk_id }}</code>
            <template v-if="source.score !== null">
              · 相关度 {{ source.score.toFixed(3) }}
            </template>
          </span>
        </div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.sources {
  margin-top: var(--kr-space-3);
  padding-top: var(--kr-space-3);
  border-top: 1px solid var(--kr-border);
}

.sources__title {
  font-size: 11.5px;
  color: var(--kr-text-muted);
  margin-bottom: var(--kr-space-2);
}

.sources__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
}

.source {
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-2);
  min-width: 0;
}

.source__index {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-size: 11px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transform: translateY(2px);
}

.source__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}

.source__name {
  font-size: 12.5px;
  color: var(--kr-text);
  word-break: break-all;
}

.source__meta {
  font-size: 11px;
  color: var(--kr-text-muted);
  word-break: break-all;
}

.source__meta code {
  font-size: 10.5px;
}

.sources--compact .source__name {
  font-size: 12px;
}

.sources--compact .sources__list {
  gap: 6px;
}
</style>
