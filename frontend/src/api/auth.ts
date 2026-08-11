/**
 * AUTH-001 frontend client helpers: status, login, logout, me.
 * Credentials always included when talking to auth endpoints.
 */
import { ApiError, apiGet, apiPost } from "./client";
import { clearCsrfToken, setCsrfToken } from "./csrf";

export type AuthStatus = {
  mode: "disabled" | "required" | string;
  required: boolean;
  authenticated: boolean;
  username?: string | null;
  csrf_header?: string;
  csrf_cookie?: string;
};

export type AuthMe = {
  authenticated: boolean;
  mode: string;
  username?: string | null;
  csrf_token?: string;
};

let _statusCache: AuthStatus | null = null;
let _statusPromise: Promise<AuthStatus> | null = null;

export function clearAuthStatusCache(): void {
  _statusCache = null;
  _statusPromise = null;
}

export async function fetchAuthStatus(force = false): Promise<AuthStatus> {
  if (!force && _statusCache) return _statusCache;
  if (!force && _statusPromise) return _statusPromise;
  _statusPromise = apiGet<AuthStatus>("/api/auth/status")
    .then((s) => {
      _statusCache = s;
      return s;
    })
    .catch((err) => {
      // If auth endpoints are unreachable, treat as disabled so local UI still loads.
      if (err instanceof ApiError && err.status === 404) {
        const fallback: AuthStatus = {
          mode: "disabled",
          required: false,
          authenticated: false,
        };
        _statusCache = fallback;
        return fallback;
      }
      throw err;
    })
    .finally(() => {
      _statusPromise = null;
    });
  return _statusPromise;
}

export async function login(username: string, password: string): Promise<{ username: string; csrf_token: string }> {
  const res = await apiPost<{ ok: boolean; username: string; csrf_token: string }>("/api/auth/login", {
    username,
    password,
  });
  if (res.csrf_token) setCsrfToken(res.csrf_token);
  clearAuthStatusCache();
  return res;
}

export async function logout(): Promise<void> {
  try {
    await apiPost<{ ok: boolean }>("/api/auth/logout", {});
  } finally {
    clearCsrfToken();
    clearAuthStatusCache();
  }
}

export async function fetchMe(): Promise<AuthMe> {
  const me = await apiGet<AuthMe>("/api/auth/me");
  if (me.csrf_token) setCsrfToken(me.csrf_token);
  return me;
}
