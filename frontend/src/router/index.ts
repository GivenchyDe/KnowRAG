import { createRouter, createWebHistory } from "vue-router";

import HomeView from "@/views/HomeView.vue";

/**
 * 路由表。
 *
 * Phase 0 只注册首页，用于验证脚手架与后端连通性。
 * 按 docs/DESIGN_IMPLEMENTATION.md 第 8.1 节的规划，后续阶段依次补入：
 *   Phase 1  /login、/register（含登录守卫）
 *   Phase 4  /chat
 *   Phase 3  /documents
 *   Phase 2  /settings
 *   Phase 4  /history
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: HomeView,
      meta: { title: "首页" },
    },
    {
      // 未匹配路径统一回到首页；Phase 1 引入登录页后改为跳转 /chat 或 /login。
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});

router.afterEach((to) => {
  const title = to.meta.title as string | undefined;
  document.title = title ? `${title} · KnowRAG` : "KnowRAG · 个人知识库问答";
});

export default router;
