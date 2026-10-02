import { ref, watch } from "vue";
import { defineStore } from "pinia";

/**
 * 通用设置（应用级本机偏好）。
 *
 * 为什么单独建 store，而不是塞进 `ui.ts`：`ui.ts` 是 Toast / 确认框的**命令式**总线
 * （`ui.toast(...)` / `await ui.confirm(...)`），生命周期只到当次交互结束；
 * 而这里放的是**需要持久化**的偏好，与 `theme.ts` 同类。把两者混在一起会让
 * ui store 既管瞬时 UI 又管长期配置，职责不清。
 *
 * 只放**不需要登录、不需要后端**的本机偏好：需要落库的配置在
 * `stores/config.ts`（模型配置）与后端 `users` 表（个人资料）。
 */

/** localStorage 键。沿用 `knowrag.` 前缀，与 `stores/theme.ts` 的 `knowrag.theme` 同一命名空间。 */
const DEV_PANEL_STORAGE_KEY = "knowrag.devPanel";

/**
 * 读取上次选择。
 *
 * 默认 `false`：右侧面板展示的是 trace_id、检索方式等调试信息，
 * 普通用户第一次打开页面不应该看到它。
 */
function readStoredFlag(key: string): boolean {
  try {
    // 只有显式存过 "true" 才算开启：任何其他值（含旧版本写入的脏数据）都退回默认关闭。
    return window.localStorage.getItem(key) === "true";
  } catch {
    // 隐私模式下访问 localStorage 会抛异常；读不到就用默认值，不该让 store 初始化失败
    return false;
  }
}

function persistFlag(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(key, String(value));
  } catch {
    // 记不住偏好不影响本次会话内的切换
  }
}

export const useSettingsStore = defineStore("settings", () => {
  /** 右侧「开发者信息」面板是否显示。 */
  const showDevPanel = ref(readStoredFlag(DEV_PANEL_STORAGE_KEY));

  function setDevPanel(value: boolean): void {
    showDevPanel.value = value;
  }

  function toggleDevPanel(): void {
    showDevPanel.value = !showDevPanel.value;
  }

  // 变更即持久化。用 watch 而不是在 setter 里写：`showDevPanel` 是 ref，
  // 将来若有别处直接改它（如快捷键），也照样会被存下来。
  watch(showDevPanel, (value) => persistFlag(DEV_PANEL_STORAGE_KEY, value));

  return { showDevPanel, setDevPanel, toggleDevPanel };
});
