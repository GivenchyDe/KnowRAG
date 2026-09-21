<script setup lang="ts">
/**
 * 应用根组件。
 *
 * Phase 0 保持最小职责：只渲染路由出口。
 * Phase 1 引入登录态后，在这里（或 layouts/AppShell.vue）按路由 meta 切换
 * 「登录页裸布局」与「工作台布局（侧边栏 + 主区）」。
 */
</script>

<template>
  <RouterView />
</template>
