<script setup lang="ts">
import { computed, ref } from "vue";

import { useAuthStore } from "@/stores/auth";

/**
 * 知识库问答主页面（Phase 1 形态）。
 *
 * 当前阶段只验证「登录后进入受保护页面」这条链路，因此：
 * - 展示已登录用户信息，证明 JWT 鉴权与 /auth/me 生效；
 * - 保留设计文档要求的页面骨架（顶部状态条 + 空状态 + 底部输入区），
 *   但输入区为禁用状态，避免出现「能输入却无响应」的空壳交互。
 *
 * 后续阶段：Phase 3 接入文档与索引状态，Phase 4 接入 SSE 流式问答与引用来源。
 */

const auth = useAuthStore();

const userCreatedAt = computed(() => {
  const raw = auth.user?.created_at;
  if (!raw) {
    return "-";
  }
  // 后端按 UTC 输出且不带时区后缀，这里补上 Z 再交给本地化格式化，
  // 否则浏览器会按本地时区解释，导致显示时间偏移。
  const date = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString();
});

/** 展示给用户的阶段说明，与 docs/DESIGN_IMPLEMENTATION.md 第 12 节对应。 */
const upcoming = [
  { phase: "Phase 2", desc: "全局模型配置：填写 LLM / Embedding / Reranker 的 API Key" },
  { phase: "Phase 3", desc: "文档上传与异步摄取：解析、切块、写入向量库" },
  { phase: "Phase 4", desc: "流式问答：SSE 输出、引用来源、会话历史" },
] as const;

const showDetails = ref(true);
</script>

<template>
  <div class="chat">
    <header class="topbar">
      <div class="topbar__title">
        <h1>知识库问答</h1>
        <p>当前处于 Phase 1：用户系统已就绪，问答能力待后续阶段接入</p>
      </div>
      <div class="topbar__status">
        <span class="kr-badge kr-badge--neutral">
          <span class="kr-dot"></span>
          模型未配置
        </span>
        <button class="toggle" type="button" @click="showDetails = !showDetails">
          {{ showDetails ? "收起详情" : "展开详情" }}
        </button>
      </div>
    </header>

    <div class="content">
      <section v-if="showDetails" class="kr-panel card">
        <h2 class="card__title">登录状态</h2>
        <dl class="info">
          <div class="info__row">
            <dt>用户名</dt>
            <dd>{{ auth.user?.username }}</dd>
          </div>
          <div class="info__row">
            <dt>用户 ID</dt>
            <dd>{{ auth.user?.id }}</dd>
          </div>
          <div class="info__row">
            <dt>邮箱</dt>
            <dd>{{ auth.user?.email ?? "未填写" }}</dd>
          </div>
          <div class="info__row">
            <dt>账号状态</dt>
            <dd>
              <span
                class="kr-badge"
                :class="auth.user?.is_active ? 'kr-badge--success' : 'kr-badge--danger'"
              >
                {{ auth.user?.is_active ? "正常" : "已禁用" }}
              </span>
            </dd>
          </div>
          <div class="info__row">
            <dt>注册时间</dt>
            <dd>{{ userCreatedAt }}</dd>
          </div>
        </dl>
        <p class="card__hint">
          以上数据来自 <code>GET /auth/me</code>，说明 JWT 鉴权与用户隔离已生效。
        </p>
      </section>

      <section class="kr-panel card empty">
        <div class="empty__mark" aria-hidden="true">◇</div>
        <h2 class="empty__title">还没有可问答的知识库</h2>
        <p class="empty__desc">
          完成后续两个阶段后，即可上传文档并基于自己的知识库提问：
        </p>
        <ul class="steps">
          <li v-for="item in upcoming" :key="item.phase" class="steps__item">
            <span class="steps__tag">{{ item.phase }}</span>
            <span class="steps__desc">{{ item.desc }}</span>
          </li>
        </ul>
      </section>
    </div>

    <footer class="composer">
      <div class="composer__box">
        <textarea
          class="composer__input"
          rows="2"
          placeholder="问答功能将在 Phase 4 开放"
          disabled
        ></textarea>
        <button class="composer__send" type="button" disabled aria-label="发送">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 12h15M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </div>
      <p class="composer__hint">禁用状态：问答链路尚未实现，避免出现无响应的输入框。</p>
    </footer>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.topbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--kr-space-4);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-bottom: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.topbar__title h1 {
  font-size: 16px;
}

.topbar__title p {
  font-size: 12.5px;
  color: var(--kr-text-secondary);
  margin-top: 2px;
}

.topbar__status {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  flex: none;
}

.toggle {
  font: inherit;
  font-size: 12.5px;
  padding: 5px 12px;
  border-radius: var(--kr-radius-pill);
  border: 1px solid var(--kr-border-strong);
  background: transparent;
  color: var(--kr-text-secondary);
  cursor: pointer;
  transition: background var(--kr-transition);
}

.toggle:hover {
  background: rgba(20, 24, 35, 0.04);
}

.content {
  flex: 1;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding: var(--kr-space-5);
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
}

.card {
  padding: var(--kr-space-5);
}

.card__title {
  font-size: 15px;
  margin-bottom: var(--kr-space-4);
}

.card__hint {
  margin-top: var(--kr-space-4);
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.card__hint code {
  font-size: 12px;
  padding: 1px 6px;
  border-radius: var(--kr-radius-sm);
  background: rgba(20, 24, 35, 0.05);
}

.info {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
}

.info__row {
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-4);
}

.info__row dt {
  flex: none;
  width: 76px;
  font-size: 12.5px;
  color: var(--kr-text-secondary);
}

.info__row dd {
  margin: 0;
  font-size: 13.5px;
  word-break: break-all;
}

.empty {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-3);
  padding: var(--kr-space-6) var(--kr-space-5);
}

.empty__mark {
  font-size: 26px;
  line-height: 1;
  color: var(--kr-text-muted);
}

.empty__title {
  font-size: 16px;
}

.empty__desc {
  font-size: 13px;
  color: var(--kr-text-secondary);
}

.steps {
  list-style: none;
  margin: var(--kr-space-2) 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
  text-align: left;
  width: 100%;
  max-width: 480px;
}

.steps__item {
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-3);
}

.steps__tag {
  flex: none;
  min-width: 68px;
  font-size: 12px;
  font-weight: 500;
  color: var(--kr-text-muted);
}

.steps__desc {
  font-size: 13px;
  color: var(--kr-text-secondary);
}

.composer {
  padding: var(--kr-space-4) var(--kr-space-5) var(--kr-space-5);
  border-top: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.composer__box {
  display: flex;
  align-items: flex-end;
  gap: var(--kr-space-3);
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding: var(--kr-space-3);
  border-radius: var(--kr-radius-lg);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
}

.composer__input {
  font: inherit;
  flex: 1;
  min-width: 0;
  border: none;
  resize: none;
  background: transparent;
  color: var(--kr-text);
}

.composer__input:disabled {
  color: var(--kr-text-muted);
  cursor: not-allowed;
}

.composer__input:focus {
  outline: none;
}

.composer__send {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: var(--kr-primary);
  cursor: pointer;
}

.composer__send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.composer__hint {
  width: 100%;
  max-width: 720px;
  margin: var(--kr-space-2) auto 0;
  font-size: 11.5px;
  color: var(--kr-text-muted);
}

@media (max-width: 640px) {
  .content {
    padding: var(--kr-space-4);
  }

  .topbar {
    flex-direction: column;
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .composer {
    padding: var(--kr-space-3) var(--kr-space-4);
  }

  .info__row {
    flex-direction: column;
    gap: 2px;
  }
}
</style>
