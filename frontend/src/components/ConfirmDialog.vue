<script setup lang="ts">
import BaseModal from "@/components/BaseModal.vue";
import { useUiStore } from "@/stores/ui";

/**
 * 全局确认框宿主。
 *
 * 等价于 Element Plus 的 `ElMessageBox.confirm`，用法：
 *
 *     if (await ui.confirm({ message: "确定退出登录？", danger: true })) { ... }
 *
 * `closeOnOverlay` 设为 false：确认框承载的是"要执行的操作"，误点遮罩就取消
 * 会让人以为点了没反应，不如让用户明确选一个按钮（Esc 仍然可以取消）。
 */
const ui = useUiStore();
</script>

<template>
  <BaseModal
    :open="ui.confirmState?.open ?? false"
    :title="ui.confirmState?.title ?? '请确认'"
    :width="400"
    :close-on-overlay="false"
    @close="ui.resolveConfirm(false)"
  >
    <p class="confirm__message">{{ ui.confirmState?.message }}</p>

    <template #footer>
      <button class="kr-btn kr-btn--ghost" type="button" @click="ui.resolveConfirm(false)">
        {{ ui.confirmState?.cancelText ?? "取消" }}
      </button>
      <button
        class="kr-btn"
        :class="ui.confirmState?.danger ? 'kr-btn--danger' : 'kr-btn--primary'"
        type="button"
        @click="ui.resolveConfirm(true)"
      >
        {{ ui.confirmState?.confirmText ?? "确定" }}
      </button>
    </template>
  </BaseModal>
</template>

<style scoped>
.confirm__message {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--kr-text-secondary);
  word-break: break-word;
}
</style>
