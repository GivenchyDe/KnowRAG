<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { useChatStore } from "@/stores/chat";

/**
 * 会话历史页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「会话历史页」——列表展示历史会话、
 * 支持搜索、删除、继续会话、显示最近更新时间。
 *
 * 与侧边栏会话列表的分工：侧边栏是「快速切换」，本页是「完整检索与管理」，
 * 因此这里提供搜索框与更大的列表空间，并展示消息条数等更多信息。
 */

const chat = useChatStore();
const router = useRouter();
const keyword = ref("");
const confirmDeleteId = ref<string | null>(null);

const filtered = computed(() => {
  const text = keyword.value.trim().toLowerCase();
  if (!text) {
    return chat.conversations;
  }
  return chat.conversations.filter((item) => item.title.toLowerCase().includes(text));
});

onMounted(() => {
  void chat.loadConversations();
});

function formatTime(raw: string): string {
  const date = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
}

async function handleContinue(conversationId: string): Promise<void> {
  await chat.openConversation(conversationId);
  await router.push("/");
}

async function handleDelete(conversationId: string): Promise<void> {
  if (confirmDeleteId.value !== conversationId) {
    // 两段式确认：删除会连带删掉该会话的全部消息，不可恢复。
    confirmDeleteId.value = conversationId;
    return;
  }
  confirmDeleteId.value = null;
  await chat.removeConversation(conversationId);
}
</script>

<template>
  <div class="history">
    <header class="page-head">
      <div>
        <h1 class="page-head__title">会话历史</h1>
        <p class="page-head__desc">共 {{ chat.conversations.length }} 个会话，可继续或删除。</p>
      </div>
      <input
        v-model="keyword"
        class="search"
        type="search"
        placeholder="搜索会话标题"
        aria-label="搜索会话标题"
      />
    </header>

    <div class="content">
      <p v-if="chat.errorMessage" class="alert alert--error" role="alert">
        {{ chat.errorMessage }}
      </p>

      <section class="kr-panel panel">
        <p v-if="chat.loadingConversations && chat.conversations.length === 0" class="state">
          正在加载…
        </p>

        <div v-else-if="chat.conversations.length === 0" class="empty">
          <p class="empty__title">还没有会话记录</p>
          <p class="empty__desc">回到问答页提出第一个问题后，会话会自动出现在这里。</p>
          <button class="btn btn--primary" type="button" @click="router.push('/')">
            去提问
          </button>
        </div>

        <p v-else-if="filtered.length === 0" class="state">没有匹配「{{ keyword }}」的会话。</p>

        <ul v-else class="list">
          <li v-for="item in filtered" :key="item.conversation_id" class="row">
            <div class="row__main">
              <span class="row__title">{{ item.title }}</span>
              <span class="row__meta">
                更新于 {{ formatTime(item.updated_at) }}
                · 创建于 {{ formatTime(item.created_at) }}
                · <code>{{ item.conversation_id.slice(0, 8) }}</code>
              </span>
            </div>
            <div class="row__ops">
              <button class="link" type="button" @click="handleContinue(item.conversation_id)">
                继续会话
              </button>
              <button
                class="link"
                :class="{ 'link--danger': confirmDeleteId === item.conversation_id }"
                type="button"
                @click="handleDelete(item.conversation_id)"
              >
                {{ confirmDeleteId === item.conversation_id ? "确认删除？" : "删除" }}
              </button>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.history {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-bottom: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.page-head__title {
  font-size: 17px;
}

.page-head__desc {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.search {
  font: inherit;
  font-size: 13px;
  flex: none;
  width: 220px;
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
}

.search:focus {
  outline: none;
  border-color: var(--kr-primary);
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}

.content {
  flex: 1;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: var(--kr-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

.panel {
  padding: var(--kr-space-5);
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-3) 0;
  border-bottom: 1px solid var(--kr-border);
}

.row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.row:first-child {
  padding-top: 0;
}

.row__main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.row__title {
  font-size: 13.5px;
  word-break: break-word;
}

.row__meta {
  font-size: 11.5px;
  color: var(--kr-text-muted);
  word-break: break-word;
}

.row__meta code {
  font-size: 10.5px;
}

.row__ops {
  display: flex;
  align-items: center;
  gap: var(--kr-space-4);
  flex: none;
}

.alert {
  font-size: 13px;
  padding: 10px 14px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

.alert--error {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}

.empty {
  text-align: center;
  padding: var(--kr-space-6) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-3);
}

.empty__title {
  font-size: 14px;
}

.empty__desc {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.state {
  font-size: 13px;
  color: var(--kr-text-secondary);
  padding: var(--kr-space-4) 0;
}

.btn {
  font: inherit;
  font-weight: 500;
  border-radius: var(--kr-radius);
  border: 1px solid transparent;
  cursor: pointer;
}

.btn--primary {
  padding: 8px 18px;
  color: var(--kr-on-primary);
  background: var(--kr-primary);
}

.btn--primary:hover {
  background: var(--kr-primary-hover);
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

@media (max-width: 640px) {
  .page-head {
    flex-direction: column;
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .search {
    width: 100%;
  }

  .content {
    padding: var(--kr-space-4);
  }

  .row {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--kr-space-2);
  }
}
</style>
