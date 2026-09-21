import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "@/App.vue";
import router from "@/router";
import "@/styles/global.css";

const app = createApp(App);

// Pinia 必须在 router 之前安装：路由守卫里会调用 useAuthStore()，
// 而 store 的实例化依赖已激活的 Pinia。
app.use(createPinia());
app.use(router);

app.mount("#app");
