import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";

/**
 * 主题（浅色 / 深色 / 跟随系统）。
 *
 * 实现方式是在 `<html>` 上写 `data-theme` 属性，配色由
 * `styles/global.css` 里的 `:root[data-theme="dark"]` 覆盖 token 提供。
 * 选 `data-theme` 而不是给每个组件传 prop：主题是全局的，
 * 走 CSS 变量才能让已有组件一次生效、不需要逐个改造。
 *
 * 存储键必须与 `index.html` 里那段防闪白的内联脚本保持一致——
 * 那段脚本要在样式表生效前就把主题定下来，否则深色用户会先看到一帧白屏。
 */

const THEME_STORAGE_KEY = "knowrag.theme";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

/** 读取上次选择。非法值一律退回 `system`，不需要额外的合法性校验。 */
function readStoredMode(): ThemeMode {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
  } catch {
    // 隐私模式下访问 localStorage 会抛异常；读不到就用默认值，不该让 store 初始化失败
    return "system";
  }
}

function persistMode(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // 记不住偏好不影响本次会话内的切换
  }
}

export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(readStoredMode());
  const systemPrefersDark = ref(false);

  /** 实际生效的主题：`system` 时由操作系统偏好决定。 */
  const resolved = computed<ResolvedTheme>(() => {
    if (mode.value === "system") {
      return systemPrefersDark.value ? "dark" : "light";
    }
    return mode.value;
  });

  let mediaQuery: MediaQueryList | null = null;

  function applyTheme(theme: ResolvedTheme): void {
    document.documentElement.dataset.theme = theme;
  }

  /**
   * 监听系统主题变化。
   *
   * 必须在 `system` 模式下也持续监听：用户可能在使用期间切换系统的深色模式
   * （定时切换、或笔记本按环境光自动切换），此时页面应当跟着变。
   * 只在初始化时读一次 `matches` 是不够的。
   */
  function bindSystemPreference(): void {
    if (mediaQuery || typeof window.matchMedia !== "function") {
      return;
    }
    mediaQuery = window.matchMedia(SYSTEM_DARK_QUERY);
    systemPrefersDark.value = mediaQuery.matches;
    mediaQuery.addEventListener("change", (event) => {
      systemPrefersDark.value = event.matches;
    });
  }

  function setMode(next: ThemeMode): void {
    mode.value = next;
  }

  bindSystemPreference();
  // immediate：store 一被创建就把属性写上去，配合 main.ts 在挂载前调用，
  // 尽可能避免"先渲染浅色再切深色"的闪动。
  watch(resolved, applyTheme, { immediate: true });
  watch(mode, persistMode);

  return { mode, resolved, systemPrefersDark, setMode };
});
