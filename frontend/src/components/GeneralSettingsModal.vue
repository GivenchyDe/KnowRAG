<script setup lang="ts">
import { ElSwitch } from "element-plus";

import BaseModal from "@/components/BaseModal.vue";
import { useSettingsStore } from "@/stores/settings";
import { useThemeStore } from "@/stores/theme";
import type { ThemeMode } from "@/stores/theme";

/**
 * 通用设置。
 *
 * 目前有主题与开发者信息两项。放在这里而不是"外观设置"，是为了后续加入
 * 语言、默认知识库开关等偏好的位置预留——那些都不属于"个人资料"。
 *
 * 两项都**立即生效**（改动即应用），不设"保存"按钮：
 * 偏好类设置是可以立刻看到结果的，多一步确认只会让人以为没生效。
 *
 * 开发者信息开关用 Element Plus 的 `ElSwitch`（按需引入，样式见 main.ts）。
 * 它的配色不需要在这里覆写：`styles/global.css` 里已把 EP 的 --el-* 变量
 * 桥接到本项目的 --kr-* token，因此深浅两套主题都会自动跟随。
 */
defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();

const theme = useThemeStore();
const settings = useSettingsStore();

/** 给 <label for> 用：点标题文字也能切换开关（EP 的开关本体较小，命中区偏窄）。 */
const DEV_SWITCH_ID = "knowrag-dev-panel-switch";

/** ElSwitch 的 change 事件会带上布尔值；这里只信任严格的 true。 */
function handleDevPanelChange(value: string | number | boolean): void {
  settings.setDevPanel(value === true);
}

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

    <section class="block">
      <h3 class="block__title">开发者</h3>

      <!-- 左侧文字 + 右侧开关。用 <div> 而不是 <label> 包整行：Element Plus 的
           Switch 内部是自己的 <input type="checkbox">，被 label 包裹时点轨道会
           **触发两次**切换；改由 label 的 for 指向开关的 id，只关联标题文字。 -->
      <div class="switch-row">
        <span class="switch-row__text">
          <label class="switch-row__label" :for="DEV_SWITCH_ID">开发者信息</label>
          <span class="switch-row__hint">
            开启后，右侧会显示引用来源、trace_id、检索方式等调试信息。普通用户建议关闭。
          </span>
        </span>
        <el-switch
          :id="DEV_SWITCH_ID"
          :model-value="settings.showDevPanel"
          @change="handleDevPanelChange"
        />
      </div>
    </section>

    <template #footer>
      <button class="kr-btn kr-btn--primary" type="button" @click="emit('close')">关闭</button>
    </template>
  </BaseModal>
</template>

<style scoped>
/* 设置项之间 20px（与个人设置弹窗保持同一节奏） */
.block + .block {
  margin-top: 20px;
}

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

/* --- 开关行：左侧文字 + 右侧开关 ---
   卡片外观与「主题」块里的 .option 完全一致（同样的圆角/边框/底色/悬停），
   这样同一个弹窗里两种控件看起来仍是一套东西。
   开关本体由 Element Plus 渲染（.el-switch），样式与主题跟随见 main.ts 与 global.css。 */
.switch-row {
  display: flex;
  /* 顶部对齐而不是垂直居中：描述折成两行时，开关应与标题对齐，
     居中会把它压到两行之间的尴尬位置。 */
  align-items: flex-start;
  gap: var(--kr-space-3);
  padding: 10px var(--kr-space-3);
  border-radius: var(--kr-radius);
  border: 1px solid var(--kr-border);
  background: var(--kr-panel-solid);
  transition:
    background var(--kr-transition),
    border-color var(--kr-transition);
}

.switch-row:hover {
  background: var(--kr-hover);
}

.switch-row__text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.switch-row__label {
  font-size: 13.5px;
  color: var(--kr-text);
  width: fit-content;
  cursor: pointer;
}

.switch-row__hint {
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--kr-text-muted);
}

/* EP 默认的开关高 32px（含上下留白），比标题行高（约 18px）大。
   与标题基线对齐而不是居中：居中会把标题压低一整行。 */
.switch-row :deep(.el-switch) {
  flex: none;
}
</style>
