<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

/**
 * 登录页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 第 1 节——简洁居中布局、轻微磨砂玻璃卡片、
 * 不要营销式 hero。
 *
 * 登录成功后优先跳回 `?redirect=` 指定的原目标页面；该参数由路由守卫写入。
 * 只接受以 `/` 开头的站内路径，防止被构造成 `//evil.com` 之类的开放重定向。
 */

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();

const username = ref("");
const password = ref("");
const submitting = ref(false);
const formError = ref<string | null>(null);

const canSubmit = computed(
  () => username.value.trim().length > 0 && password.value.length > 0 && !submitting.value,
);

/** 注册页跳转过来时带的提示，用于告知用户注册成功。 */
const registeredHint = computed(() => {
  const raw = route.query.registered;
  return typeof raw === "string" && raw.length > 0 ? `账号「${raw}」注册成功，请登录` : null;
});

/** 会话过期被自动登出时的提示。`?expired=1` 由 api/client.ts 的失效回调写入。 */
const expiredHint = computed(() =>
  route.query.expired === "1" ? "登录已过期，请重新登录" : null,
);

function resolveRedirect(): string {
  const raw = route.query.redirect;
  const target = typeof raw === "string" ? raw : "/";
  return target.startsWith("/") && !target.startsWith("//") ? target : "/";
}

async function handleSubmit(): Promise<void> {
  if (!canSubmit.value) {
    return;
  }
  submitting.value = true;
  formError.value = null;
  auth.clearError();
  try {
    await auth.login({ username: username.value.trim(), password: password.value });
    await router.replace(resolveRedirect());
  } catch (error) {
    // store 已把错误转成可展示文案，这里直接取用，避免两处维护同一套映射。
    formError.value = auth.errorMessage ?? "登录失败，请稍后重试";
    void error;
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card kr-panel">
      <header class="auth-head">
        <!-- 品牌标识：用气泡版（去掉外层圆角方框）。128px 源图按 56px 显示，留 2x 余量。
             alt 留空是因为紧随其后的标题已经说明了这是什么，图片纯装饰。 -->
        <img
          class="auth-mark"
          src="/logo/logo-bubble-128.png"
          width="56"
          height="56"
          alt=""
        />
        <h1 class="auth-title">登录 KnowRAG</h1>
        <p class="auth-subtitle">你的个人知识库问答工作台</p>
      </header>

      <form class="auth-form" novalidate @submit.prevent="handleSubmit">
        <p v-if="expiredHint" class="form-alert form-alert--warning" role="status">
          {{ expiredHint }}
        </p>
        <p v-if="registeredHint" class="form-alert form-alert--success" role="status">
          {{ registeredHint }}
        </p>

        <div class="field">
          <label class="field__label" for="login-username">用户名</label>
          <input
            id="login-username"
            v-model="username"
            class="field__input"
            type="text"
            name="username"
            autocomplete="username"
            placeholder="请输入用户名"
            :disabled="submitting"
          />
        </div>

        <div class="field">
          <label class="field__label" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            class="field__input"
            type="password"
            name="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="submitting"
          />
        </div>

        <p v-if="formError" class="form-alert form-alert--error" role="alert">{{ formError }}</p>

        <button class="btn btn--primary" type="submit" :disabled="!canSubmit">
          {{ submitting ? "登录中…" : "登录" }}
        </button>
      </form>

      <p class="auth-foot">
        还没有账号？
        <RouterLink to="/register">立即注册</RouterLink>
      </p>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--kr-space-5);
}

.auth-card {
  width: 100%;
  max-width: 400px;
  padding: var(--kr-space-6) var(--kr-space-5);
}

.auth-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-2);
  margin-bottom: var(--kr-space-5);
  text-align: center;
}

.auth-mark {
  /* 由内联 SVG 换成了位图：不再需要 color（原来靠 currentColor 上色），
     尺寸显式写死以配合 HTML 的 width/height 属性避免布局抖动。
     图片四角自带透明圆角，这里**不要**再加 border-radius，
     否则会在自带圆角之外多切一圈。 */
  width: 56px;
  height: 56px;
  display: block;
}

.auth-title {
  font-size: 20px;
}

.auth-subtitle {
  font-size: 13px;
  color: var(--kr-text-secondary);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-4);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
}

.field__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--kr-text);
}

.field__input {
  font: inherit;
  width: 100%;
  padding: 10px 14px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  transition:
    border-color var(--kr-transition),
    box-shadow var(--kr-transition);
}

.field__input::placeholder {
  color: var(--kr-text-muted);
}

.field__input:hover:not(:disabled) {
  border-color: var(--kr-input-border);
}

.field__input:focus {
  outline: none;
  border-color: var(--kr-primary);
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}

.field__input:disabled {
  background: var(--kr-sunken);
  color: var(--kr-text-muted);
  cursor: not-allowed;
}

.btn {
  font: inherit;
  font-weight: 500;
  padding: 10px 16px;
  border-radius: var(--kr-radius);
  border: 1px solid transparent;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    opacity var(--kr-transition);
}

.btn--primary {
  color: var(--kr-on-primary);
  background: var(--kr-primary);
  margin-top: var(--kr-space-1);
}

.btn--primary:hover:not(:disabled) {
  background: var(--kr-primary-hover);
}

.btn--primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.form-alert {
  font-size: 13px;
  padding: 9px 12px;
  border-radius: var(--kr-radius);
  word-break: break-word;
}

.form-alert--error {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}

.form-alert--success {
  color: var(--kr-success);
  background: var(--kr-success-soft);
}

.form-alert--warning {
  color: var(--kr-warning);
  background: var(--kr-warning-soft);
}

.auth-foot {
  margin-top: var(--kr-space-5);
  text-align: center;
  font-size: 13px;
  color: var(--kr-text-secondary);
}

@media (max-width: 480px) {
  .auth-card {
    padding: var(--kr-space-5) var(--kr-space-4);
  }
}
</style>
