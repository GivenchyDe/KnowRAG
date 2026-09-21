<script setup lang="ts">
import { RouterLink, useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

/**
 * 左侧边栏。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「应用布局」第 1 节——顶部品牌、
 * 功能入口、底部当前用户与退出登录。
 *
 * Phase 1 只放已实现的入口；会话历史列表属于 Phase 4（AppSidebar 的完整形态），
 * 文档管理与模型设置分别在 Phase 3、Phase 2。这里不渲染尚不可用的菜单项，
 * 避免用户点到空白页。
 */

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

async function handleLogout(): Promise<void> {
  auth.logout();
  await router.replace({ path: "/login" });
}

function isActive(path: string): boolean {
  return route.path === path;
}
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

    <nav class="sidebar__nav" aria-label="主导航">
      <RouterLink class="nav-item" :class="{ 'nav-item--active': isActive('/') }" to="/">
        <span class="nav-item__icon" aria-hidden="true">◆</span>
        知识库问答
      </RouterLink>
      <p class="nav-note">文档管理（Phase 3）、模型设置（Phase 2）、会话历史（Phase 4）将在后续阶段开放。</p>
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
  .nav-item span:not(.nav-item__icon),
  .nav-note,
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
