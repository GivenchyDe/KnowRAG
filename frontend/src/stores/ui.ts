import { ref } from "vue";
import { defineStore } from "pinia";

/**
 * 全局轻量 UI 状态：Toast 与确认框。
 *
 * 为什么放在 store 而不是组件里：这两者都需要**命令式**调用
 * （`ui.toast("已保存")` / `await ui.confirm({...})`），
 * 调用点分散在各个组件中，用 prop/emit 串联会污染一大串组件签名。
 * 真正的渲染交给 `ToastHost` / `ConfirmDialog` 两个宿主组件，挂在 App 根部。
 *
 * 对应 Element Plus 的 `ElMessage` / `ElMessageBox`，但本项目没有引入 UI 框架
 * （见 BaseModal.vue 的说明），因此手写一套等价的。
 */

export type ToastKind = "success" | "error" | "info";

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  /** 危险操作（如退出登录）用红色确认按钮 */
  danger?: boolean;
}

export interface ConfirmState extends ConfirmOptions {
  open: boolean;
}

/** Toast 默认停留时间。太短看不清，太长会叠一堆。 */
const TOAST_DURATION_MS = 3000;

export const useUiStore = defineStore("ui", () => {
  // --- Toast ---------------------------------------------------------------
  const toasts = ref<ToastItem[]>([]);
  let toastSeq = 0;

  function dismissToast(id: number): void {
    toasts.value = toasts.value.filter((item) => item.id !== id);
  }

  function toast(message: string, kind: ToastKind = "info", duration = TOAST_DURATION_MS): number {
    const id = ++toastSeq;
    toasts.value = [...toasts.value, { id, kind, message }];
    if (duration > 0) {
      window.setTimeout(() => dismissToast(id), duration);
    }
    return id;
  }

  // --- 确认框 --------------------------------------------------------------
  const confirmState = ref<ConfirmState | null>(null);
  /** 当前未决确认框的 resolve。同一时刻只允许一个。 */
  let settle: ((ok: boolean) => void) | null = null;

  function confirm(options: ConfirmOptions): Promise<boolean> {
    // 已有未决的确认框时先把它按「取消」结束。
    // 不这么做的话，前一个 Promise 永远不会 resolve，调用方的 await 会一直挂着。
    settle?.(false);
    settle = null;
    confirmState.value = { open: true, ...options };
    return new Promise<boolean>((resolve) => {
      settle = resolve;
    });
  }

  function resolveConfirm(ok: boolean): void {
    const pending = settle;
    settle = null;
    confirmState.value = null;
    pending?.(ok);
  }

  return { toasts, toast, dismissToast, confirmState, confirm, resolveConfirm };
});
