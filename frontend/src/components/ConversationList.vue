<script setup lang="ts">
import type { Conversation } from "@/types/chat";

/**
 * 会话列表。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 应用布局第 1 节——新建会话按钮 + 会话历史列表。
 *
 * 用 `@click` 而不是 RouterLink：会话切换不改变路由，
 * 而是切换 store 里的 conversationId。这样刷新页面仍停留在聊天页，
 * 历史会话通过会话列表重新打开。
 */

defineProps<{
  conversations: Conversation[];
  activeId: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  create: [];
  select: [conversationId: string];
  remove: [conversationId: string];
}>();

function formatTime(raw: string): string {
  // 后端按 UTC 输出且不带时区后缀，补 Z 后再本地化，否则时间会偏移。
  const date = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }
  const now = Date.now();
  const diff = now - date.getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return date.toLocaleDateString();
}
</script>

<template>
  <div class="conv">
    <button class="conv__new" type="button" @click="emit('create')">
      <span aria-hidden="true">＋</span>
      新建会话
    </button>

    <p v-if="loading && conversations.length === 0" class="conv__state">加载中…</p>
    <p v-else-if="conversations.length === 0" class="conv__state">
      还没有会话记录<br />提问后会自动创建
    </p>

    <ul v-else class="conv__list">
      <li v-for="item in conversations" :key="item.conversation_id">
        <div class="conv__item" :class="{ 'conv__item--active': item.conversation_id === activeId }">
          <button class="conv__open" type="button" @click="emit('select', item.conversation_id)">
            <span class="conv__title">{{ item.title }}</span>
            <span class="conv__time">{{ formatTime(item.updated_at) }}</span>
          </button>
          <button
            class="conv__del"
            type="button"
            title="删除会话"
            aria-label="删除会话"
            @click.stop="emit('remove', item.conversation_id)"
          >
            ×
          </button>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.conv {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
  min-height: 0;
  flex: 1;
}

.conv__new {
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--kr-space-2);
  padding: 9px 12px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  cursor: pointer;
  transition: background var(--kr-transition);
  flex: none;
}

.conv__new:hover {
  background: var(--kr-primary-soft);
  border-color: transparent;
  color: var(--kr-primary);
}

.conv__state {
  font-size: 12px;
  line-height: 1.8;
  color: var(--kr-text-muted);
  text-align: center;
  padding: var(--kr-space-4) 0;
}

.conv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv__item {
  display: flex;
  align-items: center;
  border-radius: var(--kr-radius);
  transition: background var(--kr-transition);
}

.conv__item:hover {
  background: rgba(20, 24, 35, 0.04);
}

.conv__item--active {
  background: var(--kr-primary-soft);
}

.conv__open {
  font: inherit;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 8px 4px 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
}

.conv__title {
  font-size: 13px;
  color: var(--kr-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
}

.conv__item--active .conv__title {
  color: var(--kr-primary);
  font-weight: 500;
}

.conv__time {
  font-size: 11px;
  color: var(--kr-text-muted);
}

.conv__del {
  font: inherit;
  flex: none;
  width: 24px;
  height: 24px;
  margin-right: 6px;
  border: none;
  border-radius: var(--kr-radius-sm);
  background: none;
  color: var(--kr-text-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  /* 默认隐藏，hover 时显示，避免列表看起来很杂乱 */
  opacity: 0;
  transition:
    opacity var(--kr-transition),
    color var(--kr-transition);
}

.conv__item:hover .conv__del,
.conv__del:focus-visible {
  opacity: 1;
}

.conv__del:hover {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}
</style>
