<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";

/**
 * 通用模态框。
 *
 * 项目没有引入 Element Plus 这类 UI 框架（依赖里只有 vue / pinia / vue-router /
 * markdown-it / dompurify），所以这里手写一个，颜色与圆角全部走 design tokens，
 * 与既有页面天然一致。
 *
 * 处理了模态框最容易漏掉的四件事：
 * 1. **锁定背景滚动** —— 否则滚轮会穿透到后面的页面；
 * 2. **Esc 关闭**；
 * 3. **焦点管理** —— 打开时把焦点移进面板（否则键盘用户仍在页面背后操作），
 *    关闭时还给原来的元素；
 * 4. **点击遮罩关闭时排除面板内部** —— 只有点在遮罩本身才关。
 */

const props = withDefaults(
  defineProps<{
    open: boolean;
    title?: string;
    /** 标题下的一行说明，可选 */
    description?: string;
    /** 面板宽度（px）。窄屏由 CSS 兜底为「视口宽 - 32px」 */
    width?: number;
    /** 点遮罩是否关闭。表单类弹窗可设为 false，避免误触丢失已填内容 */
    closeOnOverlay?: boolean;
  }>(),
  { title: "", description: "", width: 480, closeOnOverlay: true },
);

const emit = defineEmits<{ close: [] }>();

const panel = ref<HTMLElement | null>(null);
/** 打开前的焦点元素，关闭时还回去 */
let restoreFocusTo: HTMLElement | null = null;
/** 打开前 body 的 overflow 值 */
let previousBodyOverflow = "";

function requestClose(): void {
  emit("close");
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    event.stopPropagation();
    requestClose();
  }
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      restoreFocusTo = document.activeElement as HTMLElement | null;
      previousBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      document.addEventListener("keydown", handleKeydown);
      await nextTick();
      panel.value?.focus();
    } else {
      document.removeEventListener("keydown", handleKeydown);
      document.body.style.overflow = previousBodyOverflow;
      restoreFocusTo?.focus?.();
      restoreFocusTo = null;
    }
  },
);

// 组件在打开状态下被卸载（例如路由跳转）时，必须把监听与滚动锁清掉，
// 否则会残留一个吃 Esc 的监听器，并把页面永久锁住不能滚动。
onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleKeydown);
  document.body.style.overflow = previousBodyOverflow;
});
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="overlay"
        role="presentation"
        @click.self="closeOnOverlay && requestClose()"
      >
        <div
          ref="panel"
          class="panel"
          role="dialog"
          aria-modal="true"
          :aria-label="title || undefined"
          tabindex="-1"
          :style="{ width: `${width}px` }"
        >
          <header v-if="title || $slots.header" class="panel__head">
            <slot name="header">
              <div class="panel__titles">
                <h2 class="panel__title">{{ title }}</h2>
                <p v-if="description" class="panel__desc">{{ description }}</p>
              </div>
            </slot>
            <button class="panel__close" type="button" aria-label="关闭" @click="requestClose">
              <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
              </svg>
            </button>
          </header>

          <div class="panel__body">
            <slot />
          </div>

          <footer v-if="$slots.footer" class="panel__foot">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--kr-space-4);
  /* 遮罩也带一点模糊：与面板的磨砂质感一致，同时让背后的内容"退后" */
  background: var(--kr-overlay);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  overflow-y: auto;
}

.panel {
  /* 卡片圆角按产品要求取 16px（设计规范给的区间是 12-18px） */
  border-radius: 16px;
  border: 1px solid var(--kr-border);
  background: var(--kr-panel-solid);
  box-shadow: var(--kr-shadow);
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 2 * var(--kr-space-4));
  max-width: 100%;
  outline: none;
}

.panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--kr-space-3);
  padding: var(--kr-space-5) var(--kr-space-5) var(--kr-space-3);
  flex: none;
}

.panel__titles {
  min-width: 0;
}

.panel__title {
  font-size: 16px;
  color: var(--kr-text);
}

.panel__desc {
  margin-top: 4px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--kr-text-secondary);
}

.panel__close {
  flex: none;
  width: 28px;
  height: 28px;
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

.panel__close:hover {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.panel__body {
  padding: 0 var(--kr-space-5) var(--kr-space-5);
  overflow-y: auto;
  min-height: 0;
  scrollbar-gutter: stable;
}

.panel__foot {
  display: flex;
  justify-content: flex-end;
  gap: var(--kr-space-3);
  padding: var(--kr-space-4) var(--kr-space-5);
  border-top: 1px solid var(--kr-border);
  flex: none;
}

/* --- 过渡：淡入 + 轻微上浮，克制不夸张 --- */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--kr-transition);
}

.modal-enter-active .panel,
.modal-leave-active .panel {
  transition:
    transform var(--kr-transition),
    opacity var(--kr-transition);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .panel,
.modal-leave-to .panel {
  opacity: 0;
  transform: translateY(8px) scale(0.99);
}

@media (prefers-reduced-motion: reduce) {
  .modal-enter-active .panel,
  .modal-leave-active .panel {
    transition: opacity var(--kr-transition);
  }

  .modal-enter-from .panel,
  .modal-leave-to .panel {
    transform: none;
  }
}

@media (max-width: 640px) {
  .panel {
    width: 100% !important;
  }
}
</style>
