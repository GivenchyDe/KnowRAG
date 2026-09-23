import { createPinia } from "pinia";
import { createApp } from "vue";

import { setUnauthorizedHandler } from "@/api/client";
import App from "@/App.vue";
import router from "@/router";
import { useThemeStore } from "@/stores/theme";
import "@/styles/global.css";

const app = createApp(App);

// Pinia 必须在 router 之前安装：路由守卫里会调用 useAuthStore()，
// 而 store 的实例化依赖已激活的 Pinia。
app.use(createPinia());
app.use(router);

// 尽早实例化主题 store：它内部会立刻把 data-theme 写到 <html> 上。
// index.html 里那段内联脚本已经做过一次（防闪白），这里是兜底——
// 内联脚本被 CSP 拦掉、或用户在此期间改了系统主题时，仍能得到正确结果。
useThemeStore();

// 注册「会话彻底失效」的统一处理：access token 与 refresh token 都不可用时，
// api/client.ts 会回调这里。没有这个处理的话，token 过期后页面只会出现一堆
// 401 报错（侧边栏会话列表变空、文档页加载失败），却**不会跳回登录页**，
// 用户被卡在「看似登录着却什么都加载不出来」的状态。
setUnauthorizedHandler((reason: string) => {
  // 动态导入避免模块循环依赖：auth store 依赖 api/client，client 直接 import
  // store 会成环。
  void (async () => {
    const { useAuthStore } = await import("@/stores/auth");
    const { useChatStore } = await import("@/stores/chat");

    useAuthStore().logout();
    // 清空问答状态：否则重新登录后可能短暂看到上一个会话的残留内容。
    useChatStore().reset();

    if (router.currentRoute.value.path !== "/login") {
      await router.replace({ path: "/login", query: { expired: "1" } });
    }
    console.warn("[KnowRAG] 会话已失效，已跳转登录页：", reason);
  })();
});

app.mount("#app");
