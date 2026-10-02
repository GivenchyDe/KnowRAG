<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { useChatStore } from "@/stores/chat";
import { useSettingsStore } from "@/stores/settings";

/**
 * 会话历史页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「会话历史页」——列表展示历史会话、
 * 支持搜索、删除、继续会话、显示最近更新时间。
 *
 * 与侧边栏会话列表的分工：侧边栏是「快速切换」，本页是「完整检索与管理」，
 * 因此这里提供搜索框与更大的列表空间，并展示消息条数等更多信息。
 *
 * 会话 ID 属于调试信息，只在 `settings.showDevPanel` 打开时渲染（详见模板注释）。
 */

const chat = useChatStore();
const settings = useSettingsStore();
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
                <!-- 会话 ID 只在「通用设置 → 开发者信息」开启时显示，
                     与聊天页顶栏的会话 ID、每条回答的 trace_id 共用同一个开关。
                     两点必须注意：
                     1. **分隔符「·」要一起放进 v-if 里**。它原本是模板里的独立文本节点，
                        只藏 <code> 会留下一个悬空的「·」——「创建于 …」后面拖一个点，
                        比多显示一个 ID 更突兀；
                     2. 用 v-if 而不是 v-show：关闭时 ID 不应留在 DOM 里，
                        否则复制页面源码或用开发者工具截图仍会把它带出去。 -->
                <span v-if="settings.showDevPanel">· <code>{{ item.conversation_id.slice(0, 8) }}</code></span>
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
  /* 页头不是"框框"：去掉通栏底色与分隔线，页面里带表面的容器一律是卡片。 */
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
  /* 与弹窗里的输入框同字号（.kr-input 是 13.5px）：控件级字号全站统一，
     只有正文/标题才按层级变化 */
  font-size: 13.5px;
  flex: none;
  width: 220px;
  padding: 8px 12px;
  /* 与弹窗里的输入框同一个 token（10px），避免"搜索框和输入框圆角不一样" */
  border-radius: var(--kr-radius-input);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  transition:
    border-color var(--kr-transition),
    box-shadow var(--kr-transition);
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
  /* 左右各 8px 内边距，再用等量负外边距把高亮区向两侧扩出去：
     否则 hover 底色会紧贴文字，看起来像选中态而不是 hover 态。 */
  padding: var(--kr-space-3) var(--kr-space-2);
  margin: 0 calc(-1 * var(--kr-space-2));
  border-bottom: 1px solid var(--kr-border);
  /* 刻意**不加** border-radius：这一行只有 border-bottom，
     加圆角会让分隔线两端向上翘起（圆角描边的副作用）。
     高亮是一个内嵌在圆角卡片里的矩形，观感上更整。 */
  transition: background var(--kr-transition);
}

.row:hover {
  background: var(--kr-surface-hover);
}

.row:last-child {
  border-bottom: none;
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
  /* 与弹窗底部按钮（.kr-btn）同一套：圆角 8px、高度 36px、字号 13px。
     行高必须收紧到 1.2，否则继承 body 的 1.65 会让文字盒撑到 39px，
     min-height: 36px 就不起作用了。 */
  min-height: 36px;
  line-height: 1.2;
  font-size: 13px;
  border-radius: var(--kr-radius-btn);
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

/* 「继续会话」「删除」是文本按钮，但字号与弹窗底部按钮统一为 13px：
   同一个页面里两种字号会让"主次"关系变得不清晰——这里的主次靠颜色区分，不靠字号。 */
.link {
  font: inherit;
  font-size: 13px;
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
