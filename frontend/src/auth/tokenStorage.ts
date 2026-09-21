/**
 * token 的本地存储。
 *
 * 安全说明（偏离设计文档，需在后续阶段收敛）：
 * `docs/DESIGN_IMPLEMENTATION.md` 第 7.1 节建议生产环境使用
 * HttpOnly + Secure + SameSite Cookie 存放 token。当前改为 localStorage +
 * `Authorization: Bearer` 头，原因是 Cookie 方案必须同时配套 CSRF 防护
 * （后端签发/校验 CSRF token、前端统一携带），这部分属于 Phase 5 的安全加固范围。
 * 现在用 localStorage 是**已知的有意取舍**，不是遗漏。
 *
 * localStorage 的风险：任何 XSS 都能读取 token。因此本项目的 Markdown 渲染
 * 必须经过 DOMPurify 清洗（Phase 4 引入 markdown-it 时一并落地）。
 */

import type { TokenResponse } from "@/types/auth";

const ACCESS_TOKEN_KEY = "knowrag.access_token";
const REFRESH_TOKEN_KEY = "knowrag.refresh_token";

/**
 * 使用 localStorage 而非 sessionStorage：
 * 用户在多个标签页之间切换或重启浏览器后仍保持登录，符合知识库工具的长期使用预期。
 */
function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // 隐私模式或禁用存储时访问会抛异常，此时退化为「未登录」，不能让页面整体崩溃。
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // 存储不可用时静默失败：登录态会丢失，但不影响当前会话内的使用。
  }
}

function safeRemove(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // 同上，忽略。
  }
}

export function getAccessToken(): string | null {
  return safeGet(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return safeGet(REFRESH_TOKEN_KEY);
}

export function saveTokens(tokens: TokenResponse): void {
  safeSet(ACCESS_TOKEN_KEY, tokens.access_token);
  safeSet(REFRESH_TOKEN_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  safeRemove(ACCESS_TOKEN_KEY);
  safeRemove(REFRESH_TOKEN_KEY);
}
