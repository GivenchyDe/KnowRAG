/**
 * token 的本地存储与**过期时间解析**。
 *
 * 安全说明（偏离设计文档，属已知取舍）：
 * `docs/DESIGN_IMPLEMENTATION.md` 第 7.1 节建议生产环境使用
 * HttpOnly + Secure + SameSite Cookie。当前用 localStorage + `Authorization: Bearer`，
 * 原因是 Cookie 方案必须同时配套 CSRF 防护（后端签发/校验 CSRF token、前端统一携带），
 * 属于 Phase 5 的安全加固范围。
 *
 * localStorage 的风险：任何 XSS 都能读取 token。因此 Markdown 渲染必须经过
 * DOMPurify 清洗（已在 `src/utils/markdown.ts` 落地并用 12 组恶意载荷验证）。
 */

import type { TokenResponse } from "@/types/auth";

const ACCESS_TOKEN_KEY = "knowrag.access_token";
const REFRESH_TOKEN_KEY = "knowrag.refresh_token";

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

/**
 * 从 JWT 中读取过期时间（秒级 Unix 时间戳），解析失败返回 null。
 *
 * 为什么需要它：access token 只有 30 分钟有效期。如果只在收到 401 之后才补救，
 * 用户每半小时就会撞见一次失败的请求（侧边栏变空、页面报错），
 * 即使随后自动刷新成功了，那一瞬间的错误提示也已经显示出来了。
 * 因此在发请求前先看 exp，快过期就先刷新，把失败消灭在发生之前。
 *
 * 这里只做 base64 解码读取 payload，**不校验签名**——前端无法也不应该校验签名
 * （密钥只在服务端）。这个值仅用于「提前刷新」这一性能优化，
 * 真正的鉴权永远由后端决定，伪造 exp 只会让请求被后端拒绝。
 */
export function getTokenExpiry(token: string | null): number | null {
  if (!token) {
    return null;
  }
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  try {
    // JWT 用 base64url 编码，需要先换成标准 base64 再补齐 padding。
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = payload.padEnd(payload.length + ((4 - (payload.length % 4)) % 4), "=");
    const decoded = JSON.parse(window.atob(padded)) as { exp?: number };
    return typeof decoded.exp === "number" ? decoded.exp : null;
  } catch {
    return null;
  }
}

/**
 * 判断 access token 是否即将过期。
 *
 * `skewSeconds` 是安全余量：如果恰好卡在过期瞬间发请求，仍会收到 401，
 * 因此提前一段时间就认为「需要刷新」。
 */
export function isAccessTokenExpiring(skewSeconds = 60): boolean {
  const expiry = getTokenExpiry(getAccessToken());
  if (expiry === null) {
    // 解析不出来的 token（例如后端换了格式）交给服务端判定，
    // 这里不主动刷新，避免每次请求都多一次刷新调用。
    return false;
  }
  return expiry * 1000 - Date.now() <= skewSeconds * 1000;
}
