/**
 * UI API client — calls ONLY /api/ui/* endpoints.
 * baseURL from env; injects x-ui-key when VITE_UI_KEY is set.
 */

const _env = (import.meta as unknown as {
  env?: { VITE_API_BASE_URL?: string; VITE_UI_KEY?: string };
}).env;

const API_BASE = (_env?.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
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

export class UiApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown
  ) {
    super(message);
    this.name = "UiApiError";
  }
}

export async function uiApiGet<T>(path: string, opts?: { timeoutMs?: number }): Promise<T> {
  const url = resolveUrl(path);
  const timeoutMs = opts?.timeoutMs ?? 15_000;
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "GET",
      headers: getHeaders(),
      signal: controller.signal,
    });
    clearTimeout(id);
    const text = await res.text();
    const body = text ? (() => { try { return JSON.parse(text); } catch { return undefined; } })() : undefined;
    if (!res.ok) {
      throw new UiApiError(`UI API ${res.status}: ${res.statusText}`, res.status, body);
    }
    return (body ?? {}) as T;
  } catch (e) {
    clearTimeout(id);
    if (e instanceof UiApiError) throw e;
    throw new UiApiError(e instanceof Error ? e.message : String(e), 0);
  }
}

// DTOs
export interface UiDecisionFile {
  name: string;
  mtime_iso: string;
  size_bytes: number;
}

export interface UiDecisionFilesResponse {
  mode: "LIVE" | "MOCK";
  dir: string;
  files: UiDecisionFile[];
}

export interface UiUniverseResponse {
  source: string;
  updated_at: string;
  as_of: string;
  symbols: Array<Record<string, unknown>>;
  error?: string;
}

export interface UiSymbolDiagnosticsResponse {
  symbol: string;
  primary_reason?: string;
  verdict?: string;
  in_universe?: boolean;
  stock?: Record<string, unknown>;
  gates?: Array<Record<string, unknown>>;
  blockers?: Array<Record<string, unknown>>;
  notes?: string[];
}

export const uiEndpoints = {
  decisionFiles: (mode: "LIVE" | "MOCK") => `/api/ui/decision/files?mode=${mode}`,
  decisionLatest: (mode: "LIVE" | "MOCK") => `/api/ui/decision/latest?mode=${mode}`,
  decisionFile: (filename: string, mode: "LIVE" | "MOCK") =>
    `/api/ui/decision/file/${encodeURIComponent(filename)}?mode=${mode}`,
  universe: () => `/api/ui/universe`,
  symbolDiagnostics: (symbol: string) => `/api/ui/symbol-diagnostics?symbol=${encodeURIComponent(symbol)}`,
} as const;
