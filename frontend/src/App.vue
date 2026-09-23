<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

import ConfirmDialog from "@/components/ConfirmDialog.vue";
import ToastHost from "@/components/ToastHost.vue";
import AppShell from "@/layouts/AppShell.vue";

/**
 * 应用根组件。
 *
 * 按路由 meta.plain 决定布局：
 * - `plain: true`（登录、注册）→ 居中裸布局，不显示侧边栏；
 * - 其它 → 工作台布局（AppShell：侧边栏 + 主区）。
 *
 * Toast 与确认框挂在这里而不是 AppShell 里：登录页（plain 布局）也需要它们
 * ——登录失败的提示、退出确认都可能在那类页面上出现。
 */
const route = useRoute();
const isPlainLayout = computed(() => route.meta.plain === true);
</script>

<template>
  <RouterView v-if="isPlainLayout" />
  <AppShell v-else />

  <ToastHost />
  <ConfirmDialog />
</template>
