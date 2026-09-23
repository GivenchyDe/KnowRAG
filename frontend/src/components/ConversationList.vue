<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import type { ComponentPublicInstance } from "vue";

import type { Conversation } from "@/types/chat";

/**
 * 会话列表。
 *
 * 设计依据：`docs/UI_DESIGN_PROMPT.md` 应用布局第 1 节——新建会话按钮 + 会话历史列表。
 *
 * 用 `@click` 而不是 RouterLink：会话切换不改变路由，
 * 而是切换 store 里的 conversationId。这样刷新页面仍停留在聊天页，
 * 历史会话通过会话列表重新打开。
 *
 * ## 两点实现上的关键取舍
 *
 * 1. **菜单必须 Teleport 到 body**：会话列表是滚动容器（`overflow-y: auto`），
 *    放在列表里的绝对定位菜单会被滚动容器裁掉一半。因此菜单以 `position: fixed`
 *    浮到 body 上，坐标由按钮的 `getBoundingClientRect()` 算出。
 * 2. **按钮用绝对定位而不是 flex 兄弟节点**：flex 兄弟节点会永久占掉标题的宽度；
 *    绝对定位则让标题始终按整个行宽做省略号截断。为了文字不被按钮压住，
 *    `.conv__open` 常驻一段 `padding-right`——它是常量，所以悬停时不会有任何回流跳动。
 */

const props = defineProps<{
  conversations: Conversation[];
  activeId: string;
  loading: boolean;
}>();

const emit = defineEmits<{
  create: [];
  select: [conversationId: string];
  rename: [conversationId: string, title: string];
  togglePin: [conversationId: string, isPinned: boolean];
  remove: [conversationId: string];
}>();

/** 菜单宽度，用于把菜单右对齐到按钮并做视口边界收敛 */
const MENU_WIDTH = 152;
const MENU_HEIGHT = 132;

// --- 更多菜单 ---------------------------------------------------------------
const menuFor = ref<string | null>(null);
const menuPos = ref({ top: 0, left: 0 });
const menuEl = ref<HTMLElement | null>(null);

/** 菜单当前指向的会话。用它取标题与置顶状态，避免模板里反复 find。 */
const menuTarget = computed(
  () => props.conversations.find((item) => item.conversation_id === menuFor.value) ?? null,
);

function openMenu(conversationId: string, event: MouseEvent): void {
  const button = event.currentTarget as HTMLElement;
  const rect = button.getBoundingClientRect();

  // 右对齐到按钮；贴着视口下缘时向上弹，避免菜单跑出屏幕
  const left = Math.min(
    Math.max(8, rect.right - MENU_WIDTH),
    window.innerWidth - MENU_WIDTH - 8,
  );
  const below = rect.bottom + 4;
  const top =
    below + MENU_HEIGHT > window.innerHeight - 8
      ? Math.max(8, rect.top - MENU_HEIGHT - 4)
      : below;

  menuPos.value = { top, left };
  menuFor.value = conversationId;
}

function closeMenu(): void {
  menuFor.value = null;
}

/**
 * 点击组件外部关闭菜单。
 *
 * 用 `pointerdown` + 冒泡阶段：捕获阶段会先于按钮自身处理函数执行，
 * 导致「点按钮」被判为外部点击、菜单开不起来。
 * 判定里同时排除 `.conv__more`，这样点同一个或另一个「···」按钮时
 * 由按钮自己的处理函数决定开合，不会先被关掉。
 */
function handleDocumentPointerDown(event: PointerEvent): void {
  if (!menuFor.value) return;
  const target = event.target as HTMLElement | null;
  if (!target) return;
  if (menuEl.value?.contains(target)) return;
  if (target.closest?.(".conv__more")) return;
  closeMenu();
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    if (editingId.value) {
      cancelRename();
    }
    closeMenu();
  }
}

// --- 内联重命名 -------------------------------------------------------------
const editingId = ref<string | null>(null);
const editingTitle = ref("");
const renameInput = ref<HTMLInputElement | null>(null);
/** 防止 Enter 提交后紧接着的 blur 再提交一次 */
let renameSettled = false;

/**
 * 重命名输入框的**函数式 ref**。
 *
 * 这里不能用 `ref="renameInput"` 这种字面量写法：输入框位于 `v-for` 内部，
 * Vue 会把 v-for 里的模板 ref 收集成**数组**，于是 `renameInput.value` 拿到的是数组
 * 而不是元素，`.focus()` 静默失效——实测表现为「输入框不自动聚焦、回车提交不生效」
 * 并伴随一个 `reading 'length'` 的报错。
 * 函数式 ref 每次只把当前渲染出来的那个元素赋进来，正是这里需要的语义。
 */
function bindRenameInput(el: Element | ComponentPublicInstance | null): void {
  renameInput.value = el instanceof HTMLInputElement ? el : null;
}

async function startRename(item: Conversation): Promise<void> {
  closeMenu();
  editingId.value = item.conversation_id;
  editingTitle.value = item.title;
  renameSettled = false;
  await nextTick();
  renameInput.value?.focus();
  renameInput.value?.select();
}

function commitRename(): void {
  if (renameSettled || !editingId.value) return;
  renameSettled = true;
  const targetId = editingId.value;
  const nextTitle = editingTitle.value.trim();
  const current = props.conversations.find((item) => item.conversation_id === targetId);
  editingId.value = null;

  // 空标题或没有实际改动：直接退出编辑态，不发请求
  if (!nextTitle || nextTitle === current?.title) return;
  emit("rename", targetId, nextTitle);
}

function cancelRename(): void {
  renameSettled = true;
  editingId.value = null;
}

function handleMenuAction(action: "rename" | "pin" | "remove"): void {
  const target = menuTarget.value;
  closeMenu();
  if (!target) return;
  if (action === "rename") {
    void startRename(target);
  } else if (action === "pin") {
    emit("togglePin", target.conversation_id, !target.is_pinned);
  } else {
    emit("remove", target.conversation_id);
  }
}

function formatTime(raw: string): string {
  // 后端按 UTC 输出且不带时区后缀，补 Z 后再本地化，否则时间会偏移。
  const date = new Date(raw.endsWith("Z") ? raw : `${raw}Z`);
  if (Number.isNaN(date.getTime())) {
    return raw;
  }
  const now = Date.now();
  const diff = now - date.getTime();
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return date.toLocaleDateString();
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("keydown", handleKeydown);
  window.addEventListener("resize", closeMenu);
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  document.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("resize", closeMenu);
});
</script>

<template>
  <div class="conv">
    <button class="conv__new" type="button" @click="emit('create')">
      <span aria-hidden="true">＋</span>
      新建会话
    </button>

    <p v-if="loading && conversations.length === 0" class="conv__state">加载中…</p>
    <p v-else-if="conversations.length === 0" class="conv__state">
      还没有会话记录<br />提问后会自动创建
    </p>

    <ul v-else class="conv__list" @scroll="closeMenu">
      <li v-for="item in conversations" :key="item.conversation_id">
        <div
          class="conv__item"
          :class="{
            'conv__item--active': item.conversation_id === activeId,
            'conv__item--pinned': item.is_pinned,
          }"
        >
          <!-- 重命名态：输入框占满整行，回车提交、Esc 取消、失焦提交 -->
          <input
            v-if="editingId === item.conversation_id"
            :ref="bindRenameInput"
            v-model="editingTitle"
            class="conv__rename"
            type="text"
            maxlength="100"
            aria-label="会话名称"
            @click.stop
            @keydown.enter.prevent="commitRename"
            @keydown.esc.prevent="cancelRename"
            @blur="commitRename"
          />

          <template v-else>
            <button
              class="conv__open"
              type="button"
              @click="emit('select', item.conversation_id)"
            >
              <span class="conv__title">
                <!-- 置顶标记：只用一个极小的图形，不额外占一行、也不改字号 -->
                <svg
                  v-if="item.is_pinned"
                  class="conv__pin"
                  viewBox="0 0 24 24"
                  width="10"
                  height="10"
                  fill="currentColor"
                  aria-label="已置顶"
                >
                  <path d="M14.5 3.5l6 6-2.2 1.1-1.1 4.4-3.3-3.3-4.3 4.3-1.4-1.4 4.3-4.3-3.3-3.3 4.4-1.1z" />
                </svg>
                {{ item.title }}
              </span>
              <span class="conv__time">{{ formatTime(item.updated_at) }}</span>
            </button>

            <button
              class="conv__more"
              type="button"
              title="更多操作"
              aria-label="更多操作"
              aria-haspopup="menu"
              :aria-expanded="menuFor === item.conversation_id"
              @click.stop="openMenu(item.conversation_id, $event)"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <circle cx="5.5" cy="12" r="1.8" />
                <circle cx="12" cy="12" r="1.8" />
                <circle cx="18.5" cy="12" r="1.8" />
              </svg>
            </button>
          </template>
        </div>
      </li>
    </ul>

    <!-- 菜单 Teleport 到 body：列表是滚动容器，留在里面会被裁掉 -->
    <Teleport to="body">
      <Transition name="conv-menu">
        <div
          v-if="menuFor"
          ref="menuEl"
          class="conv-menu"
          role="menu"
          :style="{ top: `${menuPos.top}px`, left: `${menuPos.left}px`, width: `${MENU_WIDTH}px` }"
        >
          <button
            class="conv-menu__item"
            type="button"
            role="menuitem"
            @click="handleMenuAction('rename')"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M4 20h4l10-10-4-4L4 16v4z" stroke-linejoin="round" />
              <path d="M14 6l4 4" stroke-linecap="round" />
            </svg>
            <span>重命名</span>
          </button>

          <button
            class="conv-menu__item"
            type="button"
            role="menuitem"
            @click="handleMenuAction('pin')"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M9 4h6l-1 6 3 3v2H7v-2l3-3-1-6z" stroke-linejoin="round" />
              <path d="M12 15v5" stroke-linecap="round" />
            </svg>
            <span>{{ menuTarget?.is_pinned ? "取消置顶" : "置顶" }}</span>
          </button>

          <button
            class="conv-menu__item conv-menu__item--danger"
            type="button"
            role="menuitem"
            @click="handleMenuAction('remove')"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8">
              <path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <span>删除</span>
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.conv {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-3);
  min-height: 0;
  flex: 1;
}

.conv__new {
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--kr-space-2);
  padding: 9px 12px;
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border-strong);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  cursor: pointer;
  transition: background var(--kr-transition);
  flex: none;
}

.conv__new:hover {
  background: var(--kr-primary-soft);
  border-color: transparent;
  color: var(--kr-primary);
}

.conv__state {
  font-size: 12px;
  line-height: 1.8;
  color: var(--kr-text-muted);
  text-align: center;
  padding: var(--kr-space-4) 0;
}

.conv__list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  /* 预留滚动条槽位，避免会话增多时标题宽度突然变窄、文字抖动 */
  scrollbar-gutter: stable;
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv__item {
  display: flex;
  align-items: center;
  border-radius: var(--kr-radius);
  /* 按钮是绝对定位的，因此这里必须是定位上下文 */
  position: relative;
  transition: background var(--kr-transition);
}

.conv__item:hover {
  background: var(--kr-hover);
}

.conv__item--active {
  background: var(--kr-primary-soft);
}

.conv__open {
  font: inherit;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  /* 右侧常驻留出「⋯」按钮的位置：常量内边距，所以按钮显隐不会造成回流；
     同时标题的省略号截断点在悬停前后完全一致。 */
  padding: 8px 34px 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  text-align: left;
}

.conv__title {
  font-size: 13px;
  color: var(--kr-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;
  /* 置顶标记与标题同处一行，图标跟随文字颜色 */
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.conv__pin {
  flex: none;
  color: var(--kr-primary);
}

.conv__item--active .conv__title {
  color: var(--kr-primary);
  font-weight: 500;
}

.conv__time {
  font-size: 11px;
  color: var(--kr-text-muted);
}

/**
 * 「更多操作」按钮。
 *
 * 默认完全透明、悬停会话项时淡入（0.2s）。
 * **额外保留 `:focus-visible` 显示**：键盘用户无法「悬停」，
 * 若只按字面照搬「默认隐藏、悬停显示」，键盘用户将永远看不到这个按钮。
 */
.conv__more {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--kr-muted-bg);
  color: var(--kr-text-secondary);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.2s ease,
    background 0.2s ease,
    color 0.2s ease;
}

.conv__item:hover .conv__more,
.conv__more:focus-visible,
.conv__more[aria-expanded="true"] {
  opacity: 1;
}

.conv__more:hover {
  background: var(--kr-border-strong);
  color: var(--kr-text);
}

/* 重命名输入框：占满整行，视觉上取代标题与时间 */
.conv__rename {
  font: inherit;
  font-size: 13px;
  width: 100%;
  margin: 4px 6px;
  padding: 5px 8px;
  border-radius: var(--kr-radius-sm);
  border: 1px solid var(--kr-primary);
  background: var(--kr-panel-solid);
  color: var(--kr-text);
  outline: none;
  box-shadow: 0 0 0 3px var(--kr-primary-soft);
}
</style>

<style>
/* 菜单被 Teleport 到 body，因此**不能**写在 scoped 里（scoped 属性加不到它上面）。
   用独立的非 scoped 块，类名带 conv-menu 前缀避免污染。 */
.conv-menu {
  position: fixed;
  z-index: 60;
  padding: 5px;
  border-radius: 10px;
  border: 1px solid var(--kr-border);
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--kr-shadow);
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.conv-menu__item {
  font: inherit;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--kr-text-secondary);
  text-align: left;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.conv-menu__item:hover {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.conv-menu__item--danger {
  color: var(--kr-danger);
}

.conv-menu__item--danger:hover {
  background: var(--kr-danger-soft);
  color: var(--kr-danger);
}

.conv-menu-enter-active,
.conv-menu-leave-active {
  transition:
    opacity var(--kr-transition),
    transform var(--kr-transition);
}

.conv-menu-enter-from,
.conv-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
