import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";

/**
 * 路由表。
 *
 * 权限约定：默认**所有路由都需要登录**，只有显式标记 `meta.public = true` 的页面公开。
 * 采用「默认拒绝」而不是「默认放开」：漏标一个 meta 的后果是页面打不开（可立即发现），
 * 而不是把受保护页面暴露出去（很难发现）。
 *
 * 后续阶段按 `docs/DESIGN_IMPLEMENTATION.md` 第 8.1 节补入：
 *   Phase 2  /settings   Phase 3  /documents   Phase 4  /history
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "登录", public: true, plain: true },
    },
    {
      path: "/register",
      name: "register",
      component: () => import("@/views/RegisterView.vue"),
      meta: { title: "注册", public: true, plain: true },
    },
    {
      path: "/",
      name: "home",
      component: () => import("@/views/ChatView.vue"),
      meta: { title: "知识库问答" },
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: "/",
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();

  // 公开页面：已登录用户访问登录/注册页时直接送回首页，避免重复登录。
  if (to.meta.public === true) {
    if (await auth.ensureSession()) {
      return { path: "/" };
    }
    return true;
  }

  // 受保护页面：未登录则跳登录页，并把原目标路径带在 query 里，登录后跳回。
  if (!(await auth.ensureSession())) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  return true;
});

router.afterEach((to) => {
  const title = to.meta.title as string | undefined;
  document.title = title ? `${title} · KnowRAG` : "KnowRAG · 个人知识库问答";
});

export default router;
