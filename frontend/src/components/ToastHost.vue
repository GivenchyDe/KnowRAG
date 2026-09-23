<script setup lang="ts">
import { useUiStore } from "@/stores/ui";

/**
 * Toast 宿主。
 *
 * 挂在 App 根部，只负责渲染 `stores/ui.ts` 里的队列。
 * 用 `role="status"` + `aria-live="polite"`：读屏会在不打断当前朗读的前提下播报，
 * 而错误用 `role="alert"` 更合适，因此按 kind 区分。
 */
const ui = useUiStore();
</script>

<template>
  <Teleport to="body">
    <div class="toast-host">
      <TransitionGroup name="toast">
        <div
          v-for="item in ui.toasts"
          :key="item.id"
          class="toast"
          :class="`toast--${item.kind}`"
          :role="item.kind === 'error' ? 'alert' : 'status'"
          aria-live="polite"
        >
          <span class="toast__mark" aria-hidden="true">
            <svg v-if="item.kind === 'success'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4">
              <path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
            <svg v-else-if="item.kind === 'error'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4">
              <path d="M12 7v6M12 17h.01" stroke-linecap="round" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4">
              <path d="M12 11v6M12 7h.01" stroke-linecap="round" />
            </svg>
          </span>
          <span class="toast__text">{{ item.message }}</span>
          <button class="toast__close" type="button" aria-label="关闭提示" @click="ui.dismissToast(item.id)">
            ×
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-host {
  position: fixed;
  /* 顶部居中：模态框也从中间弹出，放底部容易被遮住 */
  top: var(--kr-space-5);
  left: 50%;
  transform: translateX(-50%);
  z-index: 200;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--kr-space-2);
  pointer-events: none;
  width: min(420px, calc(100vw - 32px));
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: var(--kr-space-2);
  width: 100%;
  padding: 10px var(--kr-space-3) 10px var(--kr-space-4);
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  /* 轻微玻璃拟态，与面板质感一致 */
  background: var(--kr-panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  box-shadow: var(--kr-shadow);
  font-size: 13px;
  color: var(--kr-text);
}

.toast__mark {
  flex: none;
  display: inline-flex;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  align-items: center;
  justify-content: center;
}

.toast--success .toast__mark {
  color: var(--kr-success);
  background: var(--kr-success-soft);
}

.toast--error .toast__mark {
  color: var(--kr-danger);
  background: var(--kr-danger-soft);
}

.toast--info .toast__mark {
  color: var(--kr-primary);
  background: var(--kr-primary-soft);
}

.toast__text {
  flex: 1;
  min-width: 0;
  line-height: 1.5;
  word-break: break-word;
}

.toast__close {
  flex: none;
  width: 20px;
  height: 20px;
  border: none;
  border-radius: var(--kr-radius-sm);
  background: transparent;
  color: var(--kr-text-muted);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  transition:
    background var(--kr-transition),
    color var(--kr-transition);
}

.toast__close:hover {
  background: var(--kr-hover);
  color: var(--kr-text);
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--kr-transition),
    transform var(--kr-transition);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
