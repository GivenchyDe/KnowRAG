<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { fetchHealth } from "@/api/health";
import { toErrorMessage } from "@/types/errors";

/**
 * Phase 0 首页。
 *
 * 只做两件事：
 * 1. 展示脚手架已就绪；
 * 2. 调用后端 GET /health 并展示结果，验证「前端 → 代理 → FastAPI」链路打通。
 *
 * 注意：健康检查状态只在本页使用，因此不引入 Pinia store；
 * 待 Phase 4 出现跨页面共享的鉴权、会话状态时再建立 store。
 */

type HealthState = "checking" | "online" | "offline";

const healthState = ref<HealthState>("checking");
const healthMessage = ref("正在检查后端连通性…");

const statusBadgeClass = computed(() => {
  if (healthState.value === "online") {
    return "kr-badge--success";
  }
  if (healthState.value === "offline") {
    return "kr-badge--danger";
  }
  return "kr-badge--neutral";
});

const statusText = computed(() => {
  if (healthState.value === "online") {
    return "后端已连接";
  }
  if (healthState.value === "offline") {
    return "后端未连接";
  }
  return "检查中";
});

async function checkHealth(): Promise<void> {
  healthState.value = "checking";
  healthMessage.value = "正在检查后端连通性…";
  try {
    const result = await fetchHealth();
    healthState.value = result.status === "ok" ? "online" : "offline";
    healthMessage.value =
      result.status === "ok"
        ? "GET /health 返回 {\"status\":\"ok\"}，前后端链路正常。"
        : `后端返回了非预期状态：${result.status}`;
  } catch (error) {
    healthState.value = "offline";
    healthMessage.value = toErrorMessage(error);
  }
}

/** Phase 0 验收项，逐条对应 docs/DESIGN_IMPLEMENTATION.md 第 12 节 */
const acceptanceItems = [
  { label: "GET /health 返回 {\"status\":\"ok\"}", done: true },
  { label: "前端能访问首页", done: true },
] as const;

const structureRows = [
  { path: "backend/app/main.py", desc: "FastAPI 入口，注册 /health、CORS、trace_id 中间件" },
  { path: "backend/app/core/config.py", desc: "pydantic-settings 配置，从环境变量 / .env 读取" },
  { path: "backend/app/core/logging.py", desc: "日志初始化，禁用重复的 uvicorn access log" },
  { path: "backend/app/core/errors.py", desc: "统一错误码与 {code, message, trace_id} 错误契约" },
  { path: "frontend/src/main.ts", desc: "前端入口，挂载 Vue、Router" },
  { path: "frontend/src/App.vue", desc: "根组件，Phase 0 只渲染路由出口" },
  { path: "frontend/src/router/index.ts", desc: "基础路由表与页面标题同步" },
  { path: "frontend/src/views/HomeView.vue", desc: "首页，含后端连通性自检" },
  { path: "frontend/src/api/client.ts", desc: "HTTP 客户端，统一错误契约与超时" },
  { path: "frontend/src/styles/global.css", desc: "design tokens 与通用面板 / 状态标签样式" },
] as const;

const upcomingPhases = [
  { phase: "Phase 1", desc: "用户系统：users 表、注册 / 登录 / 鉴权、登录与注册页" },
  { phase: "Phase 2", desc: "用户模型配置：API Key 加密存储、设置页" },
  { phase: "Phase 3", desc: "文档上传与异步摄取：documents / ingestion_tasks、worker" },
  { phase: "Phase 4", desc: "RAG 问答：会话与消息、SSE 流式、引用来源" },
  { phase: "Phase 5", desc: "隔离、安全、质量：A/B 用户隔离测试、评测脚本、trace_id" },
  { phase: "Phase 6", desc: "Docker 与简历包装：一键启动、截图与量化指标" },
] as const;

onMounted(() => {
  void checkHealth();
});
</script>

<template>
  <div class="home">
    <header class="topbar">
      <div class="topbar__brand">
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
          <span class="brand-tagline">RAG 个人知识库问答系统</span>
        </div>
      </div>

      <span class="kr-badge" :class="statusBadgeClass">
        <span class="kr-dot"></span>
        {{ statusText }}
      </span>
    </header>

    <main class="content">
      <section class="kr-panel hero">
        <p class="hero__eyebrow">Phase 0 · 项目脚手架</p>
        <h1 class="hero__title">脚手架已就绪</h1>
        <p class="hero__desc">
          本页只验证工程骨架能否跑通：后端 FastAPI 提供 <code>GET /health</code>，前端 Vue3 +
          Vite + TypeScript 提供基础路由与首页。用户系统、文档摄取、RAG 问答等能力尚未实现。
        </p>

        <div class="health" :class="`health--${healthState}`">
          <div class="health__head">
            <span class="kr-badge" :class="statusBadgeClass">
              <span class="kr-dot"></span>
              {{ statusText }}
            </span>
            <button class="btn btn--ghost" type="button" @click="checkHealth">重新检查</button>
          </div>
          <p class="health__message">{{ healthMessage }}</p>
        </div>
      </section>

      <div class="grid">
        <section class="kr-panel card">
          <h2 class="card__title">验收标准</h2>
          <ul class="checklist">
            <li v-for="item in acceptanceItems" :key="item.label" class="checklist__item">
              <span class="check" :class="{ 'check--done': item.done }" aria-hidden="true">
                {{ item.done ? "✓" : "" }}
              </span>
              <code class="checklist__label">{{ item.label }}</code>
            </li>
          </ul>
        </section>

        <section class="kr-panel card">
          <h2 class="card__title">启动命令</h2>
          <div class="cmd-group">
            <p class="cmd-group__label">后端（端口 8000）</p>
            <pre class="cmd"><code>cd backend
uvicorn app.main:app --reload --port 8000</code></pre>
            <p class="cmd-group__label">前端（端口 5173）</p>
            <pre class="cmd"><code>cd frontend
npm install
npm run dev</code></pre>
          </div>
        </section>
      </div>

      <section class="kr-panel card">
        <h2 class="card__title">本阶段产出目录</h2>
        <ul class="file-list">
          <li v-for="row in structureRows" :key="row.path" class="file-list__item">
            <code class="file-list__path">{{ row.path }}</code>
            <span class="file-list__desc">{{ row.desc }}</span>
          </li>
        </ul>
      </section>

      <section class="kr-panel card">
        <h2 class="card__title">后续阶段（尚未实现）</h2>
        <ul class="phase-list">
          <li v-for="item in upcomingPhases" :key="item.phase" class="phase-list__item">
            <span class="phase-list__tag">{{ item.phase }}</span>
            <span class="phase-list__desc">{{ item.desc }}</span>
          </li>
        </ul>
      </section>
    </main>

    <footer class="footer">
      <span>KnowRAG v0.1.0 · Phase 0 脚手架</span>
      <span>实现路线图见 docs/DESIGN_IMPLEMENTATION.md</span>
    </footer>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* --- 顶栏 --- */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-bottom: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.topbar__brand {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  min-width: 0;
}

.brand-mark {
  display: inline-flex;
  color: var(--kr-primary);
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
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* --- 内容区：留白充足 --- */
.content {
  flex: 1;
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: var(--kr-space-6) var(--kr-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

.hero {
  padding: var(--kr-space-6);
}

.hero__eyebrow {
  font-size: 12px;
  font-weight: 500;
  color: var(--kr-primary);
  margin-bottom: var(--kr-space-2);
}

.hero__title {
  font-size: 26px;
  margin-bottom: var(--kr-space-3);
}

.hero__desc {
  max-width: 70ch;
  color: var(--kr-text-secondary);
  margin-bottom: var(--kr-space-5);
}

.hero__desc code {
  font-size: 12.5px;
  padding: 1px 6px;
  border-radius: var(--kr-radius-sm);
  background: rgba(20, 24, 35, 0.05);
  color: var(--kr-text);
}

/* --- 连通性状态 --- */
.health {
  border: 1px solid var(--kr-border);
  border-radius: var(--kr-radius);
  padding: var(--kr-space-4);
  background: var(--kr-panel-solid);
  transition: border-color var(--kr-transition);
}

.health--online {
  border-color: rgba(22, 163, 74, 0.28);
}

.health--offline {
  border-color: rgba(220, 38, 38, 0.28);
}

.health__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--kr-space-3);
  margin-bottom: var(--kr-space-3);
}

.health__message {
  color: var(--kr-text-secondary);
  word-break: break-word;
}

/* --- 按钮 --- */
.btn {
  font: inherit;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: var(--kr-radius-pill);
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    border-color var(--kr-transition),
    color var(--kr-transition);
}

.btn--ghost {
  color: var(--kr-text-secondary);
  background: transparent;
  border-color: var(--kr-border-strong);
}

.btn--ghost:hover {
  color: var(--kr-text);
  background: rgba(20, 24, 35, 0.04);
}

/* --- 卡片 --- */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--kr-space-5);
}

.card {
  padding: var(--kr-space-5);
}

.card__title {
  font-size: 15px;
  margin-bottom: var(--kr-space-4);
}

/* --- 验收清单 --- */
.checklist {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
}

.checklist__item {
  display: flex;
  align-items: flex-start;
  gap: var(--kr-space-3);
}

.check {
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 2px;
  border-radius: 50%;
  border: 1px solid var(--kr-border-strong);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: transparent;
}

.check--done {
  color: #fff;
  background: var(--kr-success);
  border-color: transparent;
}

.checklist__label {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  word-break: break-all;
}

/* --- 命令块 --- */
.cmd-group {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
}

.cmd-group__label {
  font-size: 12px;
  color: var(--kr-text-secondary);
}

.cmd {
  margin: 0 0 var(--kr-space-3);
  padding: var(--kr-space-3) var(--kr-space-4);
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  background: rgba(20, 24, 35, 0.03);
  font-size: 12.5px;
  line-height: 1.7;
  overflow-x: auto;
  white-space: pre;
}

/* --- 文件清单 --- */
.file-list,
.phase-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
}

.file-list__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-bottom: var(--kr-space-3);
  border-bottom: 1px solid var(--kr-border);
}

.file-list__item:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.file-list__path {
  font-size: 12.5px;
  color: var(--kr-text);
  word-break: break-all;
}

.file-list__desc {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

/* --- 后续阶段 --- */
.phase-list__item {
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-3);
}

.phase-list__tag {
  flex: none;
  min-width: 74px;
  font-size: 12px;
  font-weight: 500;
  color: var(--kr-text-muted);
}

.phase-list__desc {
  color: var(--kr-text-secondary);
}

/* --- 页脚 --- */
.footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: var(--kr-space-2);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-top: 1px solid var(--kr-border);
  font-size: 12px;
  color: var(--kr-text-muted);
}

/* --- 移动端：收敛留白，避免文本溢出 --- */
@media (max-width: 640px) {
  .content {
    padding: var(--kr-space-5) var(--kr-space-4);
  }

  .hero {
    padding: var(--kr-space-5);
  }

  .hero__title {
    font-size: 22px;
  }

  .topbar {
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .brand-tagline {
    display: none;
  }

  .footer {
    flex-direction: column;
  }
}
</style>
