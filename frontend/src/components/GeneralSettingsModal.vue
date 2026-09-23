<script setup lang="ts">
import BaseModal from "@/components/BaseModal.vue";
import { useThemeStore } from "@/stores/theme";
import type { ThemeMode } from "@/stores/theme";

/**
 * 通用设置。
 *
 * 目前只有主题一项。放在这里而不是"外观设置"，是为了后续加入
 * 语言、默认知识库开关等偏好的位置预留——那些都不属于"个人资料"。
 *
 * 主题切换**立即生效**（点选即应用），不设"保存"按钮：
 * 外观类偏好是可以立刻看到结果的，多一步确认只会让人以为没生效。
 */
defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const theme = useThemeStore();

const OPTIONS: { value: ThemeMode; label: string; hint: string }[] = [
  { value: "light", label: "浅色模式", hint: "始终使用浅色界面" },
  { value: "dark", label: "深色模式", hint: "始终使用深色界面" },
  { value: "system", label: "跟随系统", hint: "随操作系统外观自动切换" },
];
</script>

<template>
  <BaseModal :open="open" title="通用设置" description="界面外观与通用偏好" :width="420" @close="emit('close')">
    <section class="block">
      <h3 class="block__title">主题</h3>

      <!-- 用 radiogroup 而不是三个按钮：这是一组互斥选项，
           原生 radio 语义能让读屏正确播报"3 选 1"以及当前选中项。 -->
      <div class="options" role="radiogroup" aria-label="主题">
        <label
          v-for="option in OPTIONS"
          :key="option.value"
          class="option"
          :class="{ 'option--active': theme.mode === option.value }"
        >
          <input
            class="option__input"
            type="radio"
            name="theme-mode"
            :value="option.value"
            :checked="theme.mode === option.value"
            @change="theme.setMode(option.value)"
          />
          <span class="option__body">
            <span class="option__label">{{ option.label }}</span>
            <span class="option__hint">{{ option.hint }}</span>
          </span>
          <!-- 选中标记：不只靠左侧圆点，避免色觉障碍用户难以分辨 -->
          <span class="option__check" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3">
              <path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
        </label>
      </div>

      <p class="kr-help">
        当前生效：<strong>{{ theme.resolved === "dark" ? "深色" : "浅色" }}</strong>
        <template v-if="theme.mode === 'system'">（跟随系统）</template>
        。选择会保存在本机浏览器中，换设备需要重新设置。
      </p>
    </section>

    <template #footer>
      <button class="kr-btn kr-btn--primary" type="button" @click="emit('close')">关闭</button>
    </template>
  </BaseModal>
</template>

<style scoped>
.block__title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--kr-text-secondary);
  margin-bottom: var(--kr-space-3);
}

.options {
  display: flex;
  flex-direction: column;
  gap: var(--kr-space-2);
  margin-bottom: var(--kr-space-3);
}

.option {
  display: flex;
  align-items: center;
  gap: var(--kr-space-3);
  padding: 10px var(--kr-space-3);
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  background: var(--kr-panel-solid);
  cursor: pointer;
  transition:
    border-color var(--kr-transition),
    background var(--kr-transition);
}

.option:hover {
  background: var(--kr-hover);
}

.option--active {
  border-color: var(--kr-primary);
  background: var(--kr-primary-soft);
}

/* 原生 radio 隐藏但保留可聚焦性：:focus-visible 时给整行描边 */
.option__input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}

.option__input:focus-visible + .option__body {
  outline: 2px solid var(--kr-primary);
  outline-offset: 3px;
  border-radius: var(--kr-radius-sm);
}

.option__body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.option__label {
  font-size: 13.5px;
  color: var(--kr-text);
}

.option--active .option__label {
  font-weight: 500;
  color: var(--kr-primary);
}

.option__hint {
  font-size: 11.5px;
  color: var(--kr-text-muted);
}

.option__check {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--kr-on-primary);
  background: var(--kr-primary);
  /* 未选中时完全透明：位置保留，避免选中瞬间文字横向跳动 */
  opacity: 0;
  transition: opacity var(--kr-transition);
}

.option--active .option__check {
  opacity: 1;
}

.kr-help strong {
  color: var(--kr-text);
  font-weight: 500;
}
</style>
