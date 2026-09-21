<script setup lang="ts">
import AppSidebar from "@/components/AppSidebar.vue";

/**
 * 工作台布局：左侧边栏 + 右侧主区。
 *
 * 登录与注册页通过路由 meta.plain 跳过本布局（见 App.vue）。
 */
</script>

<template>
  <div class="shell">
    <AppSidebar />
    <main class="shell__main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: 100%;
}

.shell__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
</style>
