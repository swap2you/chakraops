/**
 * CSRF token for AUTH-001 cookie-session mutating API calls.
 * Prefer in-memory token from login/me; fall back to readable cookie.
 */

const CSRF_COOKIE = "chakraops_csrf";

let _csrf: string | null = null;

export function setCsrfToken(token: string | null | undefined): void {
  _csrf = token?.trim() || null;
}

export function clearCsrfToken(): void {
  _csrf = null;
}

function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const parts = document.cookie.split(";").map((p) => p.trim());
  for (const p of parts) {
    if (p.startsWith(`${CSRF_COOKIE}=`)) {
      return decodeURIComponent(p.slice(CSRF_COOKIE.length + 1));
    }
  }
  return null;
}

export function getCsrfToken(): string | null {
  if (_csrf) return _csrf;
  return readCsrfCookie();
}
