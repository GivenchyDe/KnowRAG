import { computed, ref } from "vue";
import { defineStore } from "pinia";

import * as authApi from "@/api/auth";
import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from "@/auth/tokenStorage";
import { isApiError, toErrorMessage } from "@/types/errors";
import type { LoginRequest, RegisterRequest, TokenResponse, User } from "@/types/auth";

/**
 * 认证状态。
 *
 * 职责：
 * - 持有当前用户与 token；
 * - 封装登录、注册、登出、会话恢复；
 * - 对外暴露 `ensureSession()` 供路由守卫做前置校验。
 *
 * 不负责：路由跳转。跳转决策留在守卫里，store 只回答「当前是否已登录」，
 * 避免 store 反向依赖 router 形成循环引用。
 */
export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const accessToken = ref<string | null>(null);
  const refreshToken = ref<string | null>(null);
  const loading = ref(false);
  const errorMessage = ref<string | null>(null);
  /** 是否已尝试过会话恢复。用于避免每次路由跳转都发起 /auth/me 请求。 */
  const bootstrapped = ref(false);

  const isAuthenticated = computed(() => user.value !== null && accessToken.value !== null);
  const displayName = computed(() => user.value?.username ?? "");

  function applyTokens(tokens: TokenResponse): void {
    accessToken.value = tokens.access_token;
    refreshToken.value = tokens.refresh_token;
    saveTokens(tokens);
  }

  function clearSession(): void {
    user.value = null;
    accessToken.value = null;
    refreshToken.value = null;
    clearTokens();
  }

  /**
   * 用 refresh token 换取新的 token 对。
   *
   * 之所以在恢复会话时先刷新而不是先用现有 access token 请求 `/auth/me`：
   * access token 只有 30 分钟有效期，用户隔天打开页面时必然已过期，
   * 先刷新可以避免一次注定失败的请求，也避免把「过期」当作「未登录」处理。
   */
  async function refreshSession(): Promise<boolean> {
    const current = refreshToken.value;
    if (!current) {
      return false;
    }
    try {
      const tokens = await authApi.refresh(current);
      applyTokens(tokens);
      return true;
    } catch {
      // refresh token 也失效（过期或已被轮换）→ 视为未登录，清理本地残留。
      clearSession();
      return false;
    }
  }

  async function fetchCurrentUser(): Promise<boolean> {
    const token = accessToken.value;
    if (!token) {
      return false;
    }
    try {
      user.value = await authApi.fetchCurrentUser(token);
      return true;
    } catch (error) {
      // access token 可能在页面停留期间过期，这里补一次刷新再重试，
      // 否则用户会莫名其妙被踢回登录页。
      if (isApiError(error) && error.code === "UNAUTHORIZED" && (await refreshSession())) {
        try {
          user.value = await authApi.fetchCurrentUser(accessToken.value ?? "");
          return true;
        } catch {
          clearSession();
          return false;
        }
      }
      clearSession();
      return false;
    }
  }

  /** 从本地存储恢复会话。仅在应用启动时执行一次。 */
  async function bootstrap(): Promise<void> {
    if (bootstrapped.value) {
      return;
    }
    bootstrapped.value = true;

    accessToken.value = getAccessToken();
    refreshToken.value = getRefreshToken();

    if (!accessToken.value && !refreshToken.value) {
      return;
    }
    if (!accessToken.value && !(await refreshSession())) {
      return;
    }
    await fetchCurrentUser();
  }

  /** 路由守卫入口：确保已尝试恢复会话，并返回当前是否已登录。 */
  async function ensureSession(): Promise<boolean> {
    if (!bootstrapped.value) {
      await bootstrap();
    }
    return isAuthenticated.value;
  }

  async function login(payload: LoginRequest): Promise<void> {
    loading.value = true;
    errorMessage.value = null;
    try {
      const tokens = await authApi.login(payload);
      applyTokens(tokens);
      const loaded = await fetchCurrentUser();
      if (!loaded) {
        throw new Error("登录成功但无法获取用户信息，请重试");
      }
    } catch (error) {
      // 登录失败必须清掉可能已写入的 token，避免留下「有 token 无用户」的半登录状态。
      clearSession();
      errorMessage.value = toErrorMessage(error);
      throw error;
    } finally {
      loading.value = false;
    }
  }

  async function register(payload: RegisterRequest): Promise<void> {
    loading.value = true;
    errorMessage.value = null;
    try {
      await authApi.register(payload);
    } catch (error) {
      errorMessage.value = toErrorMessage(error);
      throw error;
    } finally {
      loading.value = false;
    }
  }

  function logout(): void {
    clearSession();
    errorMessage.value = null;
  }

  function clearError(): void {
    errorMessage.value = null;
  }

  return {
    user,
    accessToken,
    loading,
    errorMessage,
    isAuthenticated,
    displayName,
    bootstrap,
    ensureSession,
    refreshSession,
    fetchCurrentUser,
    login,
    register,
    logout,
    clearError,
  };
});
