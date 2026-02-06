/**
 * Phase 8.7: Single LIVE API client — fetch with timeout, ok check, JSON parse.
 * Phase 7: VITE_API_BASE_URL and VITE_API_KEY for deployment (Vercel + Railway).
 * In dev with Vite proxy: use relative /api/... so proxy forwards to backend (no VITE_API_BASE_URL needed).
 */
const _env = (import.meta as unknown as {
  env?: {
    VITE_API_BASE_URL?: string;
    VITE_API_KEY?: string;
    DEV?: boolean;
    VITE_DEBUG_API?: string;
  };
}).env;

const API_BASE = _env?.VITE_API_BASE_URL ?? "";

/** Phase 7: When set, sent as X-API-Key on every request (must match CHAKRAOPS_API_KEY on backend). */
const API_KEY = (_env?.VITE_API_KEY ?? "").trim();

const isDev = _env?.DEV === true || _env?.VITE_DEBUG_API === "true";

/** In dev we use relative /api URLs so Vite proxy can forward to backend. */
const useProxy = isDev;

/** Headers to send on every API request (e.g. X-API-Key when deployed). */
function getApiHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...extra };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

export function getResolvedUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  if (useProxy && normalized.startsWith("/api")) {
    return normalized;
  }
  const base = (API_BASE ?? "").replace(/\/$/, "");
  const p = path.startsWith("/") ? path.slice(1) : path;
  return base ? `${base}/${p}` : `/${p}`;
}

function resolvePath(path: string): string {
  return getResolvedUrl(path);
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public bodySnippet?: string,
    public body?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * GET path (relative to API_BASE), optional timeout and abort signal.
 * If signal is provided, it takes precedence over the internal timeout controller.
 * Throws ApiError on !res.ok. Re-throws AbortError for external abort handling.
 */
export async function apiGet<T>(path: string, opts?: { timeoutMs?: number; signal?: AbortSignal }): Promise<T> {
  const url = resolvePath(path);
  if (typeof console !== "undefined" && console.log) {
    console.log("[API] GET", url);
  }
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  
  // If external signal provided, use it; otherwise create internal timeout controller
  const hasExternalSignal = !!opts?.signal;
  const internalController = hasExternalSignal ? null : new AbortController();
  const signal = opts?.signal ?? internalController?.signal;
  const id = internalController ? setTimeout(() => internalController.abort(), timeoutMs) : null;

  try {
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json", ...getApiHeaders() },
      signal,
    });
    if (id) clearTimeout(id);

    let bodySnippet: string | undefined;
    const text = await res.text();
    if (text.length > 0) {
      try {
        JSON.parse(text);
      } catch {
        bodySnippet = text.slice(0, 200);
      }
    }

    if (!res.ok) {
      let parsedBody: unknown;
      try {
        parsedBody = text ? JSON.parse(text) : undefined;
      } catch {
        parsedBody = undefined;
      }
      throw new ApiError(
        `API ${res.status}: ${res.statusText}${bodySnippet ? ` — ${bodySnippet}` : ""}`,
        res.status,
        bodySnippet,
        parsedBody
      );
    }

    if (!text) return {} as T;
    return JSON.parse(text) as T;
  } catch (e) {
    if (id) clearTimeout(id);
    // Re-throw AbortError so callers can detect cancellation
    if (e instanceof Error && e.name === "AbortError") {
      throw e;
    }
    if (e instanceof ApiError) throw e;
    if (e instanceof SyntaxError) {
      throw new ApiError(`Invalid JSON from ${path}`, 0, String(e.message));
    }
    const message = e instanceof Error ? e.message : String(e);
    throw new ApiError(message, 0);
  }
}

/**
 * Phase 10: POST path with JSON body. Returns parsed JSON. Throws ApiError on !res.ok.
 * Optional headers (e.g. X-Trigger-Token for /api/ops/evaluate).
 */
export async function apiPost<T>(
  path: string,
  body: unknown,
  opts?: { timeoutMs?: number; headers?: Record<string, string> }
): Promise<T> {
  const url = resolvePath(path);
  if (typeof console !== "undefined" && console.log) {
    console.log("[API] POST", url);
  }
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...getApiHeaders(opts?.headers),
  };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(id);
    if (typeof console !== "undefined" && console.log) {
      console.log("[API] POST", url, "status=" + res.status);
    }
    const text = await res.text();
    if (!res.ok) {
      let parsed: unknown;
      try {
        parsed = text ? JSON.parse(text) : undefined;
      } catch {
        parsed = undefined;
      }
      throw new ApiError(
        `API ${res.status}: ${res.statusText}${text ? ` — ${text.slice(0, 200)}` : ""}`,
        res.status,
        text.slice(0, 200),
        parsed
      );
    }
    if (!text) return {} as T;
    return JSON.parse(text) as T;
  } catch (e) {
    clearTimeout(id);
    if (e instanceof ApiError) throw e;
    const message = e instanceof Error ? e.message : String(e);
    throw new ApiError(message, 0);
  }
}

/**
 * PUT path with JSON body. Returns parsed JSON. Throws ApiError on !res.ok.
 */
export async function apiPut<T>(
  path: string,
  body: unknown,
  opts?: { timeoutMs?: number; headers?: Record<string, string> }
): Promise<T> {
  const url = resolvePath(path);
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    ...getApiHeaders(opts?.headers),
  };
  try {
    const res = await fetch(url, {
      method: "PUT",
      headers,
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    clearTimeout(id);
    const text = await res.text();
    if (!res.ok) {
      let parsed: unknown;
      try {
        parsed = text ? JSON.parse(text) : undefined;
      } catch {
        parsed = undefined;
      }
      throw new ApiError(
        `API ${res.status}: ${res.statusText}${text ? ` — ${text.slice(0, 200)}` : ""}`,
        res.status,
        text.slice(0, 200),
        parsed
      );
    }
    if (!text) return {} as T;
    return JSON.parse(text) as T;
  } catch (e) {
    clearTimeout(id);
    if (e instanceof ApiError) throw e;
    const message = e instanceof Error ? e.message : String(e);
    throw new ApiError(message, 0);
  }
}

/**
 * DELETE path. Returns parsed JSON. Throws ApiError on !res.ok.
 */
export async function apiDelete<T>(path: string, opts?: { timeoutMs?: number }): Promise<T> {
  const url = resolvePath(path);
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "DELETE",
      headers: { Accept: "application/json", ...getApiHeaders() },
      signal: controller.signal,
    });
    clearTimeout(id);
    const text = await res.text();
    if (!res.ok) {
      throw new ApiError(
        `API ${res.status}: ${res.statusText}${text ? ` — ${text.slice(0, 200)}` : ""}`,
        res.status,
        text.slice(0, 200)
      );
    }
    if (!text) return {} as T;
    return JSON.parse(text) as T;
  } catch (e) {
    clearTimeout(id);
    if (e instanceof ApiError) throw e;
    const message = e instanceof Error ? e.message : String(e);
    throw new ApiError(message, 0);
  }
}
