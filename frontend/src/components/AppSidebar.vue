<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";

import ConversationList from "@/components/ConversationList.vue";
import GeneralSettingsModal from "@/components/GeneralSettingsModal.vue";
import ProfileModal from "@/components/ProfileModal.vue";
import UserMenu from "@/components/UserMenu.vue";
import type { UserMenuKey } from "@/components/UserMenu.vue";
import { useAuthStore } from "@/stores/auth";
import { useChatStore } from "@/stores/chat";
import { useUiStore } from "@/stores/ui";

/**
 * 左侧边栏。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md`「应用布局」第 1 节——顶部品牌、
 * 新建会话按钮、会话历史列表、功能入口、底部当前用户。
 *
 * 与最初设计的差别（有意调整）：原本「模型设置」「会话历史」是侧边栏里的
 * 独立入口，现在收进底部用户区的「更多」菜单。原因：它们都是低频设置类入口，
 * 常驻占用侧边栏会在会话多时挤压会话列表这一真正高频的区域。
 * 「文档管理」保留在侧边栏，因为它是知识库内容的主要入口。
 */

const auth = useAuthStore();
const chat = useChatStore();
const ui = useUiStore();
const router = useRouter();
const route = useRoute();

const isChatPage = (): boolean => route.path === "/";

// --- 更多菜单 ---------------------------------------------------------------
const menuOpen = ref(false);
/** 同时包住触发按钮与菜单，用于判定「点击是否发生在外部」 */
const menuWrap = ref<HTMLElement | null>(null);

const menuVisible = computed(() => menuOpen.value);

function closeMenu(): void {
  menuOpen.value = false;
}

/**
 * 点到菜单与按钮之外就关闭。
 *
 * 用 `pointerdown` 而不是 `click`：click 在按下并抬起之后才触发，
 * 若在此期间发生了布局变化（例如菜单已因别的原因关闭），判定会错位；
 * pointerdown 更贴近"用户点到了别处"这一事实。
 * 不用捕获阶段：按钮自身在 menuWrap 内，捕获阶段会先于按钮的处理函数执行，
 * 导致"点按钮关不掉"。冒泡阶段 + contains 判定即可。
 */
function handleDocumentPointerDown(event: PointerEvent): void {
  const target = event.target as Node | null;
  if (!target) return;
  if (menuWrap.value?.contains(target)) return;
  closeMenu();
}

function handleDocumentKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    closeMenu();
  }
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleDocumentKeydown);
  // 侧边栏在任何页面都会渲染，这里确保会话列表已加载
  // （store 内部无缓存判断，因此只在尚未加载过时请求一次）。
  if (chat.conversations.length === 0) {
    void chat.loadConversations();
  }
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleDocumentKeydown);
});

// --- 弹窗 -------------------------------------------------------------------
const profileOpen = ref(false);
const generalOpen = ref(false);

async function handleLogout(): Promise<void> {
  closeMenu();
  const confirmed = await ui.confirm({
    title: "退出登录",
    message: "确定要退出当前账号吗？退出后需要重新输入用户名和密码。",
    confirmText: "退出登录",
    danger: true,
  });
  if (!confirmed) {
    return;
  }
  auth.logout();
  // 登出时清空问答状态：否则下一个登录的用户会看到上一个用户的会话列表残留。
  chat.reset();
  await router.replace({ path: "/login" });
}

async function handleMenuSelect(key: UserMenuKey): Promise<void> {
  closeMenu();
  if (key === "profile") {
    profileOpen.value = true;
  } else if (key === "general") {
    generalOpen.value = true;
  } else if (key === "settings") {
    await router.push("/settings");
  } else if (key === "history") {
    await router.push("/history");
  } else if (key === "logout") {
    await handleLogout();
  }
}

// --- 新建 / 切换会话 --------------------------------------------------------
async function handleNewConversation(): Promise<void> {
  await chat.newConversation();
  if (!isChatPage()) {
    await router.push("/");
  }
}

async function handleSelectConversation(conversationId: string): Promise<void> {
  if (!isChatPage()) {
    await router.push("/");
  }
  await chat.openConversation(conversationId);
}

function isActive(path: string): boolean {
  return route.path === path;
}

const initialLetter = computed(() => (auth.displayName.slice(0, 1) || "?").toUpperCase());
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar__brand">
      <!-- 品牌标识：气泡版（去掉外层圆角方框）。64px 源图按 36px 显示。
           显示尺寸比原来的 32px 略大：圆形图标的视觉面积比同边长的方形小约 20%，
           沿用 32px 会显得比之前的方框图标"缩水"。 -->
      <img class="brand-mark" src="/logo/logo-bubble-64.png" width="36" height="36" alt="" />
      <div class="brand-text">
        <span class="brand-name">KnowRAG</span>
        <span class="brand-tagline">个人知识库问答</span>
      </div>
    </div>

    <!-- 会话区：仅聊天页显示 -->
    <div v-if="isChatPage()" class="sidebar__conv">
      <ConversationList
        :conversations="chat.conversations"
        :active-id="chat.conversationId"
        :loading="chat.loadingConversations"
        @create="handleNewConversation"
        @select="handleSelectConversation"
        @remove="chat.removeConversation($event)"
      />
    </div>

    <nav v-else class="sidebar__nav" aria-label="主导航">
      <RouterLink class="nav-item" :class="{ 'nav-item--active': true }" to="/">
        <span class="nav-item__icon" aria-hidden="true">◆</span>
        <span class="nav-item__text">返回问答</span>
      </RouterLink>
    </nav>

    <!-- 功能入口：模型设置与会话历史已移入底部「更多」菜单，这里只保留文档管理 -->
    <nav class="sidebar__links" aria-label="功能入口">
      <RouterLink class="nav-item" :class="{ 'nav-item--active': isActive('/documents') }" to="/documents">
        <span class="nav-item__icon" aria-hidden="true">▤</span>
        <span class="nav-item__text">文档管理</span>
      </RouterLink>
    </nav>

    <!-- 底部用户区：头像 + 用户名 + 更多按钮 -->
    <div class="sidebar__user">
      <div class="user">
        <span class="user__avatar" aria-hidden="true">
          <img v-if="auth.avatarUrl" :src="auth.avatarUrl" alt="" />
          <template v-else>{{ initialLetter }}</template>
        </span>
        <span class="user__name" :title="auth.displayName">{{ auth.displayName }}</span>

        <div ref="menuWrap" class="user__more-wrap">
          <button
            class="user__more"
            type="button"
            aria-label="更多"
            aria-haspopup="menu"
            :aria-expanded="menuVisible"
            @click="menuOpen = !menuOpen"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
              <circle cx="5.5" cy="12" r="1.7" />
              <circle cx="12" cy="12" r="1.7" />
              <circle cx="18.5" cy="12" r="1.7" />
            </svg>
          </button>

          <!-- 菜单向上弹出：按钮已在页面底部，向下弹会被视口裁掉 -->
          <UserMenu v-if="menuVisible" class="user__menu" @select="handleMenuSelect" />
        </div>
      </div>
    </div>

    <ProfileModal :open="profileOpen" @close="profileOpen = false" />
    <GeneralSettingsModal :open="generalOpen" @close="generalOpen = false" />
  </aside>
</template>

<style scoped>
.sidebar {
  width: 248px;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-5);
  padding: var(--kr-space-4);
  border-right: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  /* 侧边栏自身不滚动、也不被内容顶高：品牌区、功能入口、用户区固定，
     只有中间的会话列表（.conv__list）内部滚动。
     min-height: 0 是必需的——不给的话侧边栏会被列内容顶高，
     再顺着 .shell 把整页撑开。 */
  min-height: 0;
  overflow: hidden;
}

.sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  min-width: 0;
}

.brand-mark {
  /* 由内联 SVG 换成位图：保留 flex: none，
     否则 248px 侧边栏在窄屏下会把方形图片压成椭圆。 */
  width: 36px;
  height: 36px;
  display: block;
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
}

.sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
  flex: 1;
  min-height: 0;
}

/* 会话区：占据剩余空间并允许内部滚动 */
.sidebar__conv {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sidebar__links {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: none;
  padding-top: var(--kr-space-3);
  border-top: 1px solid var(--kr-border);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  padding: 9px 12px;
  border-radius: var(--kr-radius);
  color: var(--kr-text-secondary);
  font-size: 13.5px;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.nav-item:hover {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.nav-item--active {
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-weight: 500;
}

.nav-item__icon {
  font-size: 10px;
  flex: none;
}

/* --- 底部用户区 --- */
.sidebar__user {
  flex: none;
  padding-top: var(--kr-space-4);
  border-top: 1px solid var(--kr-border);
}

.user {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  min-width: 0;
}

.user__avatar {
  /* 36px 而不是 28px：过小的显示尺寸会让细节丰富的头像糊成一团。
     与品牌标识（同为 36px）保持一致，视觉重量也更平衡。
     刻意**不加** image-rendering: crisp-edges / pixelated ——
     那两个值适合像素画，用在照片上会放大噪点、反而更难看；
     缩小时默认的 auto（浏览器用高质量重采样）才是正确选择。 */
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 50%;
  overflow: hidden;
  background: var(--kr-primary-soft);
  color: var(--kr-primary);
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

/* object-fit: cover —— 非正方形头像按居中裁剪成圆形，与个人设置里的提示一致 */
.user__avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.user__name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user__more-wrap {
  /* 菜单以它为定位基准向上弹出 */
  position: relative;
  flex: none;
}

.user__more {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--kr-radius-sm);
  background: transparent;
  color: var(--kr-text-muted);
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.user__more:hover,
.user__more[aria-expanded="true"] {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.user__menu {
  position: absolute;
  /* 向上弹出，右对齐到按钮 */
  bottom: calc(100% + 6px);
  right: 0;
  z-index: 30;
}

/* 移动端：侧边栏收窄为仅图标的窄条，主区仍可用 */
@media (max-width: 768px) {
  .sidebar {
    width: 64px;
    padding: var(--kr-space-3) var(--kr-space-2);
    align-items: center;
  }

  .brand-text,
  .nav-item__text,
  .sidebar__conv,
  .sidebar__links,
  .user__name {
    display: none;
  }

  .nav-item {
    justify-content: center;
    padding: 9px;
  }

  .user {
    justify-content: center;
    flex-direction: column;
    gap: var(--kr-space-2);
  }
}
</style>
