<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { toErrorMessage } from "@/types/errors";

/**
 * 注册页。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 第 2 节——与登录页风格一致，表单校验状态清晰。
 *
 * 校验规则与后端 `backend/app/schemas/auth.py` **刻意保持一致**：
 * 前端校验只是为了即时反馈，后端仍然是唯一的权威校验方（前端可被绕过）。
 * 因此两边规则必须同步修改，否则会出现「前端放过、后端 422」的割裂体验。
 */

/** bcrypt 的输入上限为 72 字节，与后端 MAX_PASSWORD_BYTES 对应。 */
const MAX_PASSWORD_BYTES = 72;
const MIN_PASSWORD_LENGTH = 8;

const auth = useAuthStore();
const router = useRouter();

const form = reactive({
  username: "",
  email: "",
  password: "",
  confirmPassword: "",
});

const submitting = ref(false);
const formError = ref<string | null>(null);
/** 是否已经尝试提交过。未提交前不显示校验错误，避免刚进页面就满屏红字。 */
const submitted = ref(false);

/** 按 UTF-8 字节数计算密码长度，中文字符占 3 字节。 */
function byteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

const errors = computed(() => {
  const result: Record<string, string> = {};

  const username = form.username.trim();
  if (!username) {
    result.username = "请输入用户名";
  } else if (username.length < 3 || username.length > 64) {
    result.username = "用户名长度需为 3-64 个字符";
  } else if (!/^[A-Za-z0-9_-]+$/.test(username)) {
    result.username = "用户名只能包含字母、数字、下划线和连字符";
  }

  if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
    result.email = "邮箱格式不正确";
  }

  if (!form.password) {
    result.password = "请输入密码";
  } else if (form.password.length < MIN_PASSWORD_LENGTH) {
    result.password = `密码至少 ${MIN_PASSWORD_LENGTH} 位`;
  } else if (byteLength(form.password) > MAX_PASSWORD_BYTES) {
    result.password = `密码过长，UTF-8 编码后不能超过 ${MAX_PASSWORD_BYTES} 字节`;
  }

  if (!form.confirmPassword) {
    result.confirmPassword = "请再次输入密码";
  } else if (form.confirmPassword !== form.password) {
    result.confirmPassword = "两次输入的密码不一致";
  }

  return result;
});

const isValid = computed(() => Object.keys(errors.value).length === 0);

/** 字段是否应展示错误：只有提交过、或用户已经输入过该字段时才提示。 */
function showError(field: string): boolean {
  return submitted.value || Boolean(form[field as keyof typeof form]);
}

async function handleSubmit(): Promise<void> {
  submitted.value = true;
  formError.value = null;
  auth.clearError();

  if (!isValid.value) {
    return;
  }

  submitting.value = true;
  try {
    await auth.register({
      username: form.username.trim(),
      password: form.password,
      email: form.email.trim() || null,
    });
    // 注册成功后跳登录页。用 redirect 传递提示，避免引入额外的全局消息组件。
    await router.replace({ path: "/login", query: { registered: form.username.trim() } });
  } catch (error) {
    formError.value = auth.errorMessage ?? toErrorMessage(error);
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card kr-panel">
      <header class="auth-head">
        <!-- 品牌标识：与登录页保持一致——气泡版（去掉外层圆角方框），
             128px 源图按 56px 显示，留 2x 余量保证高分屏不糊。
             alt 留空是因为紧随其后的标题已经说明了这是什么，图片纯装饰。 -->
        <img
          class="auth-mark"
          src="/logo/logo-bubble-128.png"
          width="56"
          height="56"
          alt=""
        />
        <h1 class="auth-title">创建账号</h1>
        <p class="auth-subtitle">注册后即可上传文档并开始问答</p>
      </header>

      <form class="auth-form" novalidate @submit.prevent="handleSubmit">
        <div class="field">
          <label class="field__label" for="reg-username">用户名</label>
          <input
            id="reg-username"
            v-model="form.username"
            class="field__input"
            :class="{ 'field__input--invalid': showError('username') && errors.username }"
            type="text"
            name="username"
            autocomplete="username"
            placeholder="3-64 位字母、数字、下划线或连字符"
            :disabled="submitting"
          />
          <p v-if="showError('username') && errors.username" class="field__error">
            {{ errors.username }}
          </p>
        </div>

        <div class="field">
          <label class="field__label" for="reg-email">邮箱<span class="field__hint">选填</span></label>
          <input
            id="reg-email"
            v-model="form.email"
            class="field__input"
            :class="{ 'field__input--invalid': showError('email') && errors.email }"
            type="email"
            name="email"
            autocomplete="email"
            placeholder="name@example.com"
            :disabled="submitting"
          />
          <p v-if="showError('email') && errors.email" class="field__error">{{ errors.email }}</p>
        </div>

        <div class="field">
          <label class="field__label" for="reg-password">密码</label>
          <input
            id="reg-password"
            v-model="form.password"
            class="field__input"
            :class="{ 'field__input--invalid': showError('password') && errors.password }"
            type="password"
            name="new-password"
            autocomplete="new-password"
            :placeholder="`至少 ${MIN_PASSWORD_LENGTH} 位`"
            :disabled="submitting"
          />
          <p v-if="showError('password') && errors.password" class="field__error">
            {{ errors.password }}
          </p>
        </div>

        <div class="field">
          <label class="field__label" for="reg-confirm">确认密码</label>
          <input
            id="reg-confirm"
            v-model="form.confirmPassword"
            class="field__input"
            :class="{
              'field__input--invalid': showError('confirmPassword') && errors.confirmPassword,
            }"
            type="password"
            name="confirm-password"
            autocomplete="new-password"
            placeholder="再次输入密码"
            :disabled="submitting"
          />
          <p v-if="showError('confirmPassword') && errors.confirmPassword" class="field__error">
            {{ errors.confirmPassword }}
          </p>
        </div>

        <p v-if="formError" class="form-alert form-alert--error" role="alert">{{ formError }}</p>

        <button class="btn btn--primary" type="submit" :disabled="submitting">
          {{ submitting ? "注册中…" : "注册" }}
        </button>
      </form>

      <p class="auth-foot">
        已有账号？
        <RouterLink to="/login">返回登录</RouterLink>
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
  max-width: 420px;
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
  /* 与登录页一致：由内联 SVG 换成位图，不再需要 color（原来靠 currentColor 上色），
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
  display: flex;
  align-items: baseline;
  gap: var(--kr-space-2);
}

.field__hint {
  font-size: 11px;
  font-weight: 400;
  color: var(--kr-text-muted);
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

.field__input--invalid {
  border-color: var(--kr-danger);
}

.field__input--invalid:focus {
  border-color: var(--kr-danger);
  box-shadow: 0 0 0 3px var(--kr-danger-soft);
}

.field__input:disabled {
  background: var(--kr-sunken);
  color: var(--kr-text-muted);
  cursor: not-allowed;
}

.field__error {
  font-size: 12px;
  color: var(--kr-danger);
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
