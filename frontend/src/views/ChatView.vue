<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useConfigStore } from "@/stores/config";
import { useDocumentStore } from "@/stores/documents";
import { IndexStatus } from "@/types/documents";

/**
 * 知识库问答主页面（Phase 3 形态）。
 *
 * 当前阶段验证的是三条链路：
 * - 登录后进入受保护页面（Phase 1）；
 * - 模型配置是否就绪（Phase 2）；
 * - 知识库是否已建立可用索引（Phase 3）。
 *
 * 输入区仍然禁用：问答链路属于 Phase 4，提前放开会变成「能输入却没响应」的空壳。
 * 但索引状态会提前展示，让用户知道现在缺的是文档还是模型。
 */

const auth = useAuthStore();
const configStore = useConfigStore();
const documentStore = useDocumentStore();

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

const modelLabel = computed(() => {
  const config = configStore.config;
  if (!config) {
    return "读取中…";
  }
  return `${config.llm_model}（${config.llm_provider}）`;
});

const keyReady = computed(() => configStore.config?.llm_api_key_masked != null);

/** 模型服务是否就绪：需要 provider 目录里存在该取值且已配置 Key。 */
const modelReady = computed(() => configStore.config !== null && keyReady.value);

/** 知识库索引是否可用。可用 = 有已索引文档且后端判定状态为 ready。 */
const indexReady = computed(() => documentStore.indexInfo?.status === IndexStatus.READY);

const indexMessage = computed(
  () => documentStore.indexInfo?.message ?? "正在读取知识库状态…",
);

/** 展示给用户的阶段说明，与 docs/DESIGN_IMPLEMENTATION.md 第 12 节对应。 */
const upcoming = [
  { phase: "Phase 4", desc: "流式问答：SSE 输出、引用来源、会话历史" },
] as const;

const showDetails = ref(true);

onMounted(() => {
  // 配置已在设置页加载过时不会重复请求（store 内部有缓存判断）。
  void configStore.load().catch(() => {
    // 失败时 store 已记录 errorMessage，页面用「读取失败」状态展示即可。
  });
  void documentStore.loadIndexStatus();
});
</script>

<template>
  <div class="chat">
    <header class="topbar">
      <div class="topbar__title">
        <h1>知识库问答</h1>
        <p>当前为 Phase 2：用户系统与模型配置已就绪，问答能力待后续阶段接入</p>
      </div>
      <div class="topbar__status">
        <span class="kr-badge" :class="modelReady ? 'kr-badge--success' : 'kr-badge--warning'">
          <span class="kr-dot"></span>
          {{ modelReady ? "模型已配置" : "模型待配置" }}
        </span>
        <span class="kr-badge" :class="indexReady ? 'kr-badge--success' : 'kr-badge--warning'">
          <span class="kr-dot"></span>
          {{ indexReady ? "知识库就绪" : "知识库未就绪" }}
        </span>
        <button class="toggle" type="button" @click="showDetails = !showDetails">
          {{ showDetails ? "收起详情" : "展开详情" }}
        </button>
      </div>
    </header>

    <div class="content">
      <section v-if="showDetails" class="kr-panel card">
        <h2 class="card__title">当前状态</h2>
        <dl class="info">
          <div class="info__row">
            <dt>登录用户</dt>
            <dd>
              {{ auth.user?.username }}
              <span class="info__muted">（ID {{ auth.user?.id }}，注册于 {{ userCreatedAt }}）</span>
            </dd>
          </div>
          <div class="info__row">
            <dt>对话模型</dt>
            <dd>{{ modelLabel }}</dd>
          </div>
          <div class="info__row">
            <dt>API Key</dt>
            <dd>
              <template v-if="keyReady">
                <code class="info__code">{{ configStore.config?.llm_api_key_masked }}</code>
                <span class="info__muted">已加密存储</span>
              </template>
              <template v-else>
                <span class="info__warn">尚未填写</span>
                <RouterLink class="info__link" to="/settings">去设置</RouterLink>
              </template>
            </dd>
          </div>
          <div class="info__row">
            <dt>向量模型</dt>
            <dd>
              {{ configStore.config ? `${configStore.config.embed_model}（${configStore.config.embed_provider}）` : "读取中…" }}
            </dd>
          </div>
          <div class="info__row">
            <dt>重排模型</dt>
            <dd>
              {{ configStore.config ? `${configStore.config.rerank_model}（${configStore.config.rerank_provider}）` : "读取中…" }}
            </dd>
          </div>
          <div class="info__row">
            <dt>知识库</dt>
            <dd>
              <span :class="indexReady ? '' : 'info__warn'">{{ indexMessage }}</span>
              <RouterLink class="info__link" to="/documents">
                {{ documentStore.hasDocuments ? "管理文档" : "去上传文档" }}
              </RouterLink>
            </dd>
          </div>
        </dl>
        <p class="card__hint">
          以上配置来自 <code>GET /api/config/model</code>，可在
          <RouterLink class="info__link" to="/settings">模型设置</RouterLink> 中修改。
        </p>
      </section>

      <section class="kr-panel card empty">
        <div class="empty__mark" aria-hidden="true">◇</div>
        <h2 class="empty__title">问答能力将在 Phase 4 开放</h2>
        <p class="empty__desc">
          知识库已可用，检索与流式回答尚未接入。届时即可基于你上传的文档提问。
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
  word-break: break-word;
  min-width: 0;
}

.info__muted {
  font-size: 12px;
  color: var(--kr-text-muted);
  margin-left: var(--kr-space-2);
}

.info__code {
  font-size: 12.5px;
  padding: 1px 6px;
  border-radius: var(--kr-radius-sm);
  background: rgba(20, 24, 35, 0.05);
}

.info__warn {
  color: var(--kr-warning);
}

.info__link {
  margin-left: var(--kr-space-3);
  font-size: 12.5px;
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
