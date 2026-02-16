/**
 * UI API client — fetch-based. No fallback logic. Throws on non-200.
 * Base URL from VITE_API_BASE_URL (VITE_API_BASE fallback). x-ui-key from VITE_UI_KEY.
 */

const _env = (import.meta as unknown as {
  env?: { VITE_API_BASE_URL?: string; VITE_API_BASE?: string; VITE_UI_KEY?: string };
}).env;

const API_BASE = (
  (_env?.VITE_API_BASE_URL ?? _env?.VITE_API_BASE) ?? ""
).replace(/\/$/, "");
const UI_KEY = (_env?.VITE_UI_KEY ?? "").trim();

function resolveUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${p}` : p;
}

function getHeaders(): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (UI_KEY) h["x-ui-key"] = UI_KEY;
  return h;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function jsonHeaders(): Record<string, string> {
  const h = getHeaders();
  h["Content-Type"] = "application/json";
  return h;
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "GET",
    headers: getHeaders(),
  });
  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });
  const text = await res.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}
