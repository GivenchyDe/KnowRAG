<script setup lang="ts">
import { onMounted } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import ConversationList from "@/components/ConversationList.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";

/**
 * 左侧边栏。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「应用布局」第 1 节——顶部品牌、
 * 新建会话按钮、会话历史列表、功能入口、底部当前用户与退出登录。
 *
 * 会话列表只在聊天页显示：在文档页/设置页里展示会话列表会让侧边栏显得杂乱，
 * 且点击后要跳转页面，与「切换会话」的预期不符。
 */

const auth = useAuthStore();
const chat = useChatStore();
const router = useRouter();
const route = useRoute();

const isChatPage = () => route.path === "/";

async function handleLogout(): Promise<void> {
  auth.logout();
  // 登出时清空问答状态：否则下一个登录的用户会看到上一个用户的会话列表残留。
  chat.reset();
  await router.replace({ path: "/login" });
}

function isActive(path: string): boolean {
  return route.path === path;
}

async function handleNewConversation(): Promise<void> {
  await chat.newConversation();
  if (!isChatPage()) {
    await router.push("/");
  }
}

async function handleSelectConversation(conversationId: string): Promise<void> {
  if (!isChatPage()) {
    await router.push("/");
  }
  await chat.openConversation(conversationId);
}

onMounted(() => {
  // 侧边栏在任何页面都会渲染，这里确保会话列表已加载（store 内部无缓存判断，
  // 因此只在尚未加载过时请求一次）。
  if (chat.conversations.length === 0) {
    void chat.loadConversations();
  }
});
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="20" height="20">
          <rect width="32" height="32" rx="9" fill="currentColor" />
          <path
            d="M11 10.5h10M11 16h6.5M11 21.5h4"
            stroke="#fff"
            stroke-width="2.2"
            stroke-linecap="round"
          />
        </svg>
      </span>
      <div class="brand-text">
        <span class="brand-name">KnowRAG</span>
        <span class="brand-tagline">个人知识库问答</span>
      </div>
    </div>

    <!-- 会话区：仅聊天页显示 -->
    <div v-if="isChatPage()" class="sidebar__conv">
      <ConversationList
        :conversations="chat.conversations"
        :active-id="chat.conversationId"
        :loading="chat.loadingConversations"
        @create="handleNewConversation"
        @select="handleSelectConversation"
        @remove="chat.removeConversation($event)"
      />
    </div>

    <nav v-else class="sidebar__nav" aria-label="主导航">
      <RouterLink class="nav-item" :class="{ 'nav-item--active': true }" to="/">
        <span class="nav-item__icon" aria-hidden="true">◆</span>
        <span class="nav-item__text">返回问答</span>
      </RouterLink>
    </nav>

    <nav class="sidebar__links" aria-label="功能入口">
      <RouterLink class="nav-item" :class="{ 'nav-item--active': isActive('/documents') }" to="/documents">
        <span class="nav-item__icon" aria-hidden="true">▤</span>
        <span class="nav-item__text">文档管理</span>
      </RouterLink>
      <RouterLink class="nav-item" :class="{ 'nav-item--active': isActive('/history') }" to="/history">
        <span class="nav-item__icon" aria-hidden="true">≡</span>
        <span class="nav-item__text">会话历史</span>
      </RouterLink>
      <RouterLink class="nav-item" :class="{ 'nav-item--active': isActive('/settings') }" to="/settings">
        <span class="nav-item__icon" aria-hidden="true">⚙</span>
        <span class="nav-item__text">模型设置</span>
      </RouterLink>
    </nav>

    <div class="sidebar__user">
      <div class="user-info">
        <span class="user-avatar" aria-hidden="true">
          {{ auth.displayName.slice(0, 1).toUpperCase() || "?" }}
        </span>
        <span class="user-name">{{ auth.displayName }}</span>
      </div>
      <button class="logout" type="button" @click="handleLogout">退出登录</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 248px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
  padding: var(--kr-space-4);
  border-right: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  /* 侧边栏自身不滚动、也不被内容顶高：品牌区、功能入口、用户区固定，
     只有中间的会话列表（.conv__list）内部滚动。
     min-height: 0 是必需的——不给的话侧边栏会被列内容顶高，
     再顺着 .shell 把整页撑开。 */
  min-height: 0;
  overflow: hidden;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  min-width: 0;
}

.brand-mark {
  color: var(--kr-primary);
  display: inline-flex;
  flex: none;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
}

.brand-tagline {
  font-size: 12px;
  color: var(--kr-text-secondary);
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
  flex: 1;
  min-height: 0;
}

/* 会话区：占据剩余空间并允许内部滚动 */
.sidebar__conv {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sidebar__links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: none;
  padding-top: var(--kr-space-3);
  border-top: 1px solid var(--kr-border);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  padding: 9px 12px;
  border-radius: var(--kr-radius);
  color: var(--kr-text-secondary);
  font-size: 13.5px;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.nav-item:hover {
  background: rgba(20, 24, 35, 0.04);
  color: var(--kr-text);
}

.nav-item--active {
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-weight: 500;
}

.nav-item__icon {
  font-size: 10px;
  flex: none;
}

.nav-note {
  margin-top: var(--kr-space-3);
  padding: 0 12px;
  font-size: 11.5px;
  line-height: 1.7;
  color: var(--kr-text-muted);
}

.sidebar__user {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
  padding-top: var(--kr-space-4);
  border-top: 1px solid var(--kr-border);
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  min-width: 0;
}

.user-avatar {
  width: 28px;
  height: 28px;
  flex: none;
  border-radius: 50%;
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.user-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout {
  font: inherit;
  font-size: 12.5px;
  padding: 7px 12px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border-strong);
  background: transparent;
  color: var(--kr-text-secondary);
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.logout:hover {
  background: rgba(20, 24, 35, 0.04);
  color: var(--kr-text);
}

/* 移动端：侧边栏收窄为仅图标的窄条，主区仍可用 */
@media (max-width: 768px) {
  .sidebar {
    width: 64px;
    padding: var(--kr-space-3) var(--kr-space-2);
    align-items: center;
  }

  .brand-text,
  .nav-item__text,
  .nav-note,
  .sidebar__conv,
  .sidebar__links,
  .user-name,
  .logout {
    display: none;
  }

  .nav-item {
    justify-content: center;
    padding: 9px;
  }
}
</style>
