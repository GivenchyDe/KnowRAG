<script setup lang="ts">
/**
 * 用户「更多」弹出菜单（纯展示组件）。
 *
 * 只负责渲染与派发选择事件：定位、开合、点击外部关闭都由父组件
 * （AppSidebar）控制——因为触发按钮在父组件里，把「外部」的判定放在
 * 同时拥有按钮和菜单的一方最不容易出错。
 *
 * 之所以不用原生 `<select>`：菜单需要图标、分组分隔线与危险色，
 * 且要贴在按钮上方弹出，原生控件做不到这些。
 */

export type UserMenuKey = "profile" | "general" | "settings" | "history" | "logout";

interface MenuEntry {
  key: UserMenuKey;
  label: string;
  /** 与其上一条之间画分隔线 */
  dividerBefore?: boolean;
  danger?: boolean;
}

const ENTRIES: MenuEntry[] = [
  { key: "profile", label: "个人设置" },
  { key: "general", label: "通用设置" },
  { key: "settings", label: "模型设置", dividerBefore: true },
  { key: "history", label: "会话历史" },
  { key: "logout", label: "退出登录", dividerBefore: true, danger: true },
];

const emit = defineEmits<{ select: [key: UserMenuKey] }>();
</script>

<template>
  <div class="menu" role="menu">
    <template v-for="entry in ENTRIES" :key="entry.key">
      <div v-if="entry.dividerBefore" class="menu__divider" role="separator"></div>
      <button
        class="menu__item"
        :class="{ 'menu__item--danger': entry.danger }"
        type="button"
        role="menuitem"
        @click="emit('select', entry.key)"
      >
        <span class="menu__icon" aria-hidden="true">
          <svg v-if="entry.key === 'profile'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="12" cy="8.5" r="3.5" />
            <path d="M4.5 20c0-3.6 3.4-6 7.5-6s7.5 2.4 7.5 6" stroke-linecap="round" />
          </svg>
          <svg v-else-if="entry.key === 'general'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M4 7h10M18 7h2M4 17h4M12 17h8" stroke-linecap="round" />
            <circle cx="16" cy="7" r="2.2" />
            <circle cx="10" cy="17" r="2.2" />
          </svg>
          <svg v-else-if="entry.key === 'settings'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 3.5v2M12 18.5v2M20.5 12h-2M5.5 12h-2M17.9 6.1l-1.4 1.4M7.5 16.5l-1.4 1.4M17.9 17.9l-1.4-1.4M7.5 7.5L6.1 6.1" stroke-linecap="round" />
          </svg>
          <svg v-else-if="entry.key === 'history'" viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
            <circle cx="12" cy="12" r="8.5" />
            <path d="M12 7.5V12l3 2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg v-else viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M15 4h3.5A1.5 1.5 0 0 1 20 5.5v13a1.5 1.5 0 0 1-1.5 1.5H15" stroke-linecap="round" />
            <path d="M10 8l-4 4 4 4M6 12h9" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
        <span class="menu__label">{{ entry.label }}</span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.menu {
  min-width: 176px;
  padding: 5px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  /* 轻微玻璃拟态：与侧边栏、面板同一套质感 */
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--kr-shadow);
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.menu__divider {
  height: 1px;
  margin: 4px 6px;
  background: var(--kr-border);
}

.menu__item {
  font: inherit;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: var(--kr-radius-sm);
  background: transparent;
  color: var(--kr-text-secondary);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.menu__item:hover {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.menu__item--danger {
  color: var(--kr-danger);
}

.menu__item--danger:hover {
  /* 危险项 hover 用淡红底而不是普通灰底，让"这一项不一样"更明确 */
  background: var(--kr-danger-soft);
  color: var(--kr-danger);
}

.menu__icon {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
}

.menu__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
