/**
 * UI API client — fetch-based. No fallback logic. Throws on non-200.
 * Base URL from VITE_API_BASE_URL (VITE_API_BASE fallback). x-ui-key from VITE_UI_KEY.
 * AUTH-001: credentials include + CSRF header on mutating requests.
 */

import { getCsrfToken } from "./csrf";

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

function getHeaders(mutative = false): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (UI_KEY) h["x-ui-key"] = UI_KEY;
  if (mutative) {
    const csrf = getCsrfToken();
    if (csrf) h["X-CSRF-Token"] = csrf;
  }
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

function jsonHeaders(mutative = true): Record<string, string> {
  const h = getHeaders(mutative);
  h["Content-Type"] = "application/json";
  return h;
}

async function parseBody(res: Response): Promise<unknown> {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : undefined;
  } catch {
    return undefined;
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "GET",
    headers: getHeaders(false),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "POST",
    headers: jsonHeaders(true),
    body: JSON.stringify(payload),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

/** POST with no body (e.g. R26.5 monthly close generate). */
export async function apiPostNoBody<T>(path: string): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "POST",
    headers: getHeaders(true),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

export async function apiPatch<T>(path: string, payload: unknown): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "PATCH",
    headers: jsonHeaders(true),
    body: JSON.stringify(payload),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

export async function apiPut<T>(path: string, payload: unknown): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "PUT",
    headers: jsonHeaders(true),
    body: JSON.stringify(payload),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

/** POST to path and return response as text (e.g. CSV export). */
export async function apiPostText(path: string): Promise<string> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "POST",
    headers: getHeaders(true),
    body: undefined,
    credentials: "include",
  });
  const text = await res.text();
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, text);
  }
  return text;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "DELETE",
    headers: getHeaders(true),
    credentials: "include",
  });
  const body = await parseBody(res);
  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return (body ?? {}) as T;
}

/** R26.5: GET and return response as Blob (e.g. file download). */
export async function apiGetBlob(path: string): Promise<Blob> {
  const url = resolveUrl(path);
  const res = await fetch(url, {
    method: "GET",
    headers: getHeaders(false),
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text();
    let body: unknown;
    try {
      body = text ? JSON.parse(text) : undefined;
    } catch {
      body = text;
    }
    throw new ApiError(`API ${res.status}: ${res.statusText}`, res.status, body);
  }
  return res.blob();
}
