<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

import BaseModal from "@/components/BaseModal.vue";
import { useAuthStore } from "@/stores/auth";
import { useUiStore } from "@/stores/ui";
import { toErrorMessage } from "@/types/errors";

/**
 * 个人设置。
 *
 * 三个要点：
 * 1. **头像先本地预览、点保存才真正上传**。选完文件立刻上传的话，
 *    用户点了「取消」却发现头像已经换了，是很糟的体验。
 * 2. **只提交改过的字段**。后端按「请求体里出现了哪些键」决定更新什么；
 *    把没改的字段也带上，会让它被重新校验一次（例如历史上超长的用户名
 *    会在只改邮箱时被判为超长而保存失败）。
 * 3. **前端校验只是为了即时反馈**，真正的约束在后端（长度、字符集、唯一性、
 *    图片魔数）；前端拦不住的都要能显示后端的报错原文。
 */

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const auth = useAuthStore();
const ui = useUiStore();

/** 头像大小限制，与后端 `settings.max_avatar_bytes` 保持一致 */
const MAX_AVATAR_BYTES = 2 * 1024 * 1024;
const ALLOWED_AVATAR_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"];

const USERNAME_MIN = 2;
const USERNAME_MAX = 20;
const USERNAME_PATTERN = /^[A-Za-z0-9_-]+$/;

const username = ref("");
const email = ref("");
const saving = ref(false);
const formError = ref<string | null>(null);

/** 待上传的头像文件；为 null 表示本次没有换头像 */
const pendingAvatar = ref<File | null>(null);
/** 本地预览用的 object URL */
const avatarPreview = ref<string | null>(null);
const dragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const initial = computed(() => ({
  username: auth.user?.username ?? "",
  email: auth.user?.email ?? "",
}));

const usernameError = computed(() => {
  const value = username.value.trim();
  if (!value) return "用户名不能为空";
  if (value.length < USERNAME_MIN) return `用户名至少 ${USERNAME_MIN} 个字符`;
  if (value.length > USERNAME_MAX) return `用户名最多 ${USERNAME_MAX} 个字符`;
  if (!USERNAME_PATTERN.test(value)) return "用户名只能包含字母、数字、下划线和连字符";
  return null;
});

const emailError = computed(() => {
  const value = email.value.trim();
  if (!value) return null; // 邮箱可以留空（与注册一致）
  // 有意保持宽松：只做「看起来像邮箱」的判断，真正的合法性由后端 EmailStr 决定。
  // 前端用严格正则经常把合法邮箱判错，反而挡住用户。
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? null : "邮箱格式不正确";
});

const trimmedUsername = computed(() => username.value.trim());
const trimmedEmail = computed(() => email.value.trim());

/** 是否有实际改动——没有改动就没必要发请求，也避免空 PATCH 被后端拒绝 */
const isDirty = computed(
  () =>
    pendingAvatar.value !== null ||
    trimmedUsername.value !== initial.value.username ||
    trimmedEmail.value !== initial.value.email,
);

const canSave = computed(
  () => !saving.value && isDirty.value && !usernameError.value && !emailError.value,
);

/** 当前展示的头像：优先本地预览，其次后端已保存的，最后为空（显示文字头像） */
const displayAvatar = computed(() => avatarPreview.value ?? auth.avatarUrl);
const initialLetter = computed(() => (auth.displayName || "?").slice(0, 1).toUpperCase());

function releasePreview(): void {
  if (avatarPreview.value) {
    URL.revokeObjectURL(avatarPreview.value);
    avatarPreview.value = null;
  }
}

/** 用表单初始值重置本地状态。每次打开都重置，避免上次取消留下的残留。 */
function resetForm(): void {
  releasePreview();
  pendingAvatar.value = null;
  username.value = initial.value.username;
  email.value = initial.value.email;
  formError.value = null;
  dragging.value = false;
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetForm();
    } else {
      releasePreview();
    }
  },
);

// object URL 不受组件生命周期管理，必须显式释放，否则每换一次头像就泄漏一份内存
onBeforeUnmount(releasePreview);

function pickFile(): void {
  fileInput.value?.click();
}

function acceptFile(file: File | undefined | null): void {
  if (!file) return;
  formError.value = null;

  const extension = `.${(file.name.split(".").pop() ?? "").toLowerCase()}`;
  // 本地只做**粗筛**：明显不是图片的直接拦掉，省一次无谓的上传。
  // 真实格式一律由后端按文件头判定 —— 浏览器是按**扩展名**推断 MIME 的，
  // 「后缀名不对但内容完好的图片」（例如截图工具存出的 xx.png 其实是 JPEG）
  // 很常见，本地按 MIME 硬拦会把这些正常文件误伤。
  const looksLikeImage =
    file.type.startsWith("image/") || ALLOWED_AVATAR_EXTENSIONS.includes(extension);
  if (!looksLikeImage) {
    ui.toast("请选择 JPG / PNG / WebP 格式的图片文件", "error");
    return;
  }
  if (file.size > MAX_AVATAR_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1);
    ui.toast(`头像不能超过 2MB，当前 ${mb}MB`, "error");
    return;
  }
  if (file.size === 0) {
    ui.toast("这个文件是空的，请重新选择", "error");
    return;
  }

  releasePreview();
  pendingAvatar.value = file;
  avatarPreview.value = URL.createObjectURL(file);
}

function handleInputChange(event: Event): void {
  const target = event.target as HTMLInputElement;
  acceptFile(target.files?.[0]);
  // 清空 value，保证「连续选同一个文件」也能再次触发 change
  target.value = "";
}

function handleDrop(event: DragEvent): void {
  dragging.value = false;
  acceptFile(event.dataTransfer?.files?.[0]);
}

function clearAvatar(): void {
  releasePreview();
  pendingAvatar.value = null;
}

async function handleSave(): Promise<void> {
  if (!canSave.value) return;
  saving.value = true;
  formError.value = null;
  try {
    // 1) 先传头像：它最容易失败（格式/大小/网络），失败就不该继续改资料，
    //    否则会出现"名字改了、头像没改"的半成功状态，用户难以判断。
    if (pendingAvatar.value) {
      await auth.uploadAvatar(pendingAvatar.value);
      pendingAvatar.value = null;
    }

    // 2) 只提交真正变化的字段
    const changes: { username?: string; email?: string | null } = {};
    if (trimmedUsername.value !== initial.value.username) {
      changes.username = trimmedUsername.value;
    }
    if (trimmedEmail.value !== initial.value.email) {
      changes.email = trimmedEmail.value || null;
    }
    if (Object.keys(changes).length > 0) {
      await auth.updateProfile(changes);
    }

    ui.toast("个人资料已保存", "success");
    emit("close");
  } catch (error) {
    // 后端会给可读文案（如「该用户名已被占用」），直接把原文显示出来
    const message = toErrorMessage(error);
    formError.value = message;
    ui.toast(message, "error");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <BaseModal
    :open="open"
    title="个人设置"
    description="修改头像、用户名与邮箱"
    :width="460"
    @close="emit('close')"
  >
    <!-- 头像 -->
    <section class="block">
      <h3 class="block__title">头像</h3>
      <div class="avatar-row">
        <div class="avatar-preview" :class="{ 'avatar-preview--drag': dragging }">
          <img v-if="displayAvatar" :src="displayAvatar" alt="当前头像" />
          <span v-else class="avatar-preview__letter">{{ initialLetter }}</span>
        </div>

        <div
          class="dropzone"
          :class="{ 'dropzone--active': dragging }"
          role="button"
          tabindex="0"
          @click="pickFile"
          @keydown.enter.prevent="pickFile"
          @keydown.space.prevent="pickFile"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="handleDrop"
        >
          <p class="dropzone__title">点击选择，或把图片拖到这里</p>
          <p class="dropzone__hint">支持 JPG / PNG / WebP，不超过 2MB</p>
        </div>
      </div>

      <p class="kr-help">
        建议使用正方形图片（256×256 以上）。非正方形图片会按居中裁剪显示为圆形，
        上传前无需自己裁剪。
      </p>
      <button v-if="pendingAvatar" class="link-btn" type="button" @click="clearAvatar">
        撤销本次选择（{{ pendingAvatar.name }}）
      </button>

      <input
        ref="fileInput"
        class="sr-only"
        type="file"
        accept="image/jpeg,image/png,image/webp"
        @change="handleInputChange"
      />
    </section>

    <!-- 用户名 -->
    <section class="block">
      <label class="kr-label" for="profile-username">用户名</label>
      <div class="input-row">
        <input
          id="profile-username"
          v-model="username"
          class="kr-input"
          :class="{ 'kr-input--invalid': usernameError && username.length > 0 }"
          type="text"
          autocomplete="username"
          :placeholder="`${USERNAME_MIN}-${USERNAME_MAX} 个字符`"
          :disabled="saving"
        />
        <button
          v-if="username.length > 0"
          class="clear-btn"
          type="button"
          aria-label="清空用户名"
          :disabled="saving"
          @click="username = ''"
        >
          ×
        </button>
      </div>
      <p v-if="usernameError && username.length > 0" class="kr-error">{{ usernameError }}</p>
      <p v-else class="kr-help">{{ USERNAME_MIN }}-{{ USERNAME_MAX }} 个字符，仅限字母、数字、下划线和连字符</p>
    </section>

    <!-- 邮箱 -->
    <section class="block">
      <label class="kr-label" for="profile-email">邮箱</label>
      <div class="input-row">
        <input
          id="profile-email"
          v-model="email"
          class="kr-input"
          :class="{ 'kr-input--invalid': emailError }"
          type="email"
          autocomplete="email"
          placeholder="留空表示不设置邮箱"
          :disabled="saving"
        />
        <button
          v-if="email.length > 0"
          class="clear-btn"
          type="button"
          aria-label="清空邮箱"
          :disabled="saving"
          @click="email = ''"
        >
          ×
        </button>
      </div>
      <p v-if="emailError" class="kr-error">{{ emailError }}</p>
      <p v-else class="kr-help">用于将来找回账号，可留空</p>
    </section>

    <p v-if="formError" class="form-error" role="alert">{{ formError }}</p>

    <template #footer>
      <button class="kr-btn kr-btn--ghost" type="button" :disabled="saving" @click="emit('close')">
        取消
      </button>
      <button class="kr-btn kr-btn--primary" type="button" :disabled="!canSave" @click="handleSave">
        {{ saving ? "保存中…" : "保存" }}
      </button>
    </template>
  </BaseModal>
</template>

<style scoped>
.block {
  margin-bottom: var(--kr-space-5);
}

.block:last-of-type {
  margin-bottom: var(--kr-space-2);
}

.block__title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--kr-text-secondary);
  margin-bottom: var(--kr-space-3);
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: var(--kr-space-4);
}

.avatar-preview {
  /* 80px：预览要能看清细节，太小的话用户无法判断自己选的图对不对。
     与侧边栏一样，不加 image-rendering —— 照片缩小用浏览器的默认重采样最好。 */
  flex: none;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-size: 28px;
  font-weight: 600;
  border: 1px solid var(--kr-border);
  transition: box-shadow var(--kr-transition);
}

.avatar-preview--drag {
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}

/* object-fit: cover —— 非正方形图片按居中裁剪显示，与下方提示一致 */
.avatar-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.dropzone {
  flex: 1;
  min-width: 0;
  padding: var(--kr-space-3) var(--kr-space-4);
  border-radius: var(--kr-radius);
  border: 1px dashed var(--kr-border-strong);
  background: var(--kr-sunken);
  cursor: pointer;
  transition:
    border-color var(--kr-transition),
    background var(--kr-transition);
}

.dropzone:hover,
.dropzone:focus-visible {
  border-color: var(--kr-primary);
  background: var(--kr-primary-soft);
}

.dropzone--active {
  border-color: var(--kr-primary);
  border-style: solid;
  background: var(--kr-primary-soft);
}

.dropzone__title {
  font-size: 13px;
  color: var(--kr-text);
}

.dropzone__hint {
  margin-top: 2px;
  font-size: 11.5px;
  color: var(--kr-text-muted);
}

.input-row {
  position: relative;
}

/* 给清空按钮留出位置，避免文字被盖住 */
.input-row .kr-input {
  padding-right: 34px;
}

.clear-btn {
  position: absolute;
  top: 50%;
  right: 8px;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: var(--kr-muted-bg);
  color: var(--kr-text-secondary);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.clear-btn:hover:not(:disabled) {
  background: var(--kr-border-strong);
  color: var(--kr-text);
}

.link-btn {
  margin-top: var(--kr-space-2);
  padding: 0;
  border: none;
  background: none;
  font: inherit;
  font-size: 11.5px;
  color: var(--kr-primary);
  cursor: pointer;
  text-decoration: underline;
}

.form-error {
  margin-top: var(--kr-space-2);
  padding: 8px 12px;
  border-radius: var(--kr-radius);
  background: var(--kr-danger-soft);
  color: var(--kr-danger);
  font-size: 12.5px;
  line-height: 1.6;
  word-break: break-word;
}

/* 视觉隐藏但仍可被辅助技术与 click() 触达 */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
