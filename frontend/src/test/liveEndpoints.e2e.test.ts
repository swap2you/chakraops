/**
 * LIVE endpoint e2e tests — real HTTP against LIVE API.
 * Skip unless LIVE_API_BASE_URL (or VITE_API_BASE_URL) is set.
 * Run: LIVE_API_BASE_URL=http://localhost:8000 npm test -- liveEndpoints
 * On failure, prints URL + status + body snippet for debugging.
 */
import { describe, it, expect } from "vitest";

const API_BASE = (process.env.LIVE_API_BASE_URL ?? process.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TIMEOUT_MS = 15_000;
const EVAL_TOKEN = process.env.EVALUATE_TRIGGER_TOKEN ?? process.env.VITE_EVALUATE_TRIGGER_TOKEN ?? "";

function resolveUrl(path: string): string {
  return API_BASE ? `${API_BASE}${path.startsWith("/") ? path : "/" + path}` : path;
}

async function fetchGet(path: string): Promise<{ status: number; body: unknown; url: string }> {
  const url = resolveUrl(path);
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { method: "GET", headers: { Accept: "application/json" }, signal: controller.signal });
    clearTimeout(id);
    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text.slice(0, 300);
      }
    }
    return { status: res.status, body, url };
  } catch (e) {
    clearTimeout(id);
    throw new Error(`GET ${url} failed: ${e instanceof Error ? e.message : String(e)}`);
  }
}

async function fetchPost(path: string, body: unknown): Promise<{ status: number; body: unknown; url: string }> {
  const url = resolveUrl(path);
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "application/json" };
  if (EVAL_TOKEN) headers["X-Trigger-Token"] = EVAL_TOKEN;
  try {
    const res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    clearTimeout(id);
    const text = await res.text();
    let parsed: unknown = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text.slice(0, 300);
      }
    }
    return { status: res.status, body: parsed, url };
  } catch (e) {
    clearTimeout(id);
    throw new Error(`POST ${url} failed: ${e instanceof Error ? e.message : String(e)}`);
  }
}

describe("LIVE endpoints (e2e)", () => {
  it.skipIf(!API_BASE)("requires LIVE_API_BASE_URL or VITE_API_BASE_URL", () => {
    expect(API_BASE).toBeTruthy();
  });

  it.skipIf(!API_BASE)("GET /api/view/universe returns 200 with symbols or 503 when ORATS down", async () => {
    const { status, body, url } = await fetchGet("/api/view/universe");
    if (status === 404) {
      throw new Error(`404 ${url} — body: ${JSON.stringify(body).slice(0, 200)}`);
    }
    expect([200, 503]).toContain(status);
    const data = body as Record<string, unknown>;
    expect(data).toBeDefined();
    if (status === 200) {
      expect(Array.isArray(data?.symbols)).toBe(true);
      expect("updated_at" in data).toBe(true);
    } else {
      expect("detail" in data).toBe(true);
    }
  });

  it.skipIf(!API_BASE)("GET /api/view/symbol-diagnostics?symbol=SPY returns 200 with fetched_at or 503", async () => {
    const { status, body, url } = await fetchGet("/api/view/symbol-diagnostics?symbol=SPY");
    if (status === 404) {
      throw new Error(`404 ${url} — body: ${JSON.stringify(body).slice(0, 200)}`);
    }
    expect([200, 503]).toContain(status);
    const data = body as Record<string, unknown>;
    if (status === 200) {
      expect(data?.symbol).toBe("SPY");
      expect("fetched_at" in data).toBe(true);
      expect("status" in data || "recommendation" in data).toBe(true);
    } else {
      expect("detail" in data).toBe(true);
    }
  });

  it.skipIf(!API_BASE)("GET /api/ops/data-health returns 200 with provider, status, entitlement", async () => {
    const { status, body, url } = await fetchGet("/api/ops/data-health");
    if (status === 404) {
      throw new Error(`404 ${url} — body: ${JSON.stringify(body).slice(0, 200)}`);
    }
    expect(status).toBe(200);
    const data = body as Record<string, unknown>;
    expect(data?.provider).toBe("ORATS");
    expect("status" in data).toBe(true);
    expect("entitlement" in data).toBe(true);
  });

  it.skipIf(!API_BASE)("POST /api/ops/refresh-live-data returns 200 with fetched_at or 503", async () => {
    const { status, body, url } = await fetchPost("/api/ops/refresh-live-data", {});
    expect([200, 503]).toContain(status);
    const data = body as Record<string, unknown>;
    if (status === 200) {
      expect("fetched_at" in data).toBe(true);
    } else {
      expect("detail" in data).toBe(true);
    }
  });

  it.skipIf(!API_BASE)("GET /api/ops/status returns 200 with last_run_at, next_run_at, cadence_minutes", async () => {
    const { status, body, url } = await fetchGet("/api/ops/status");
    if (status === 404) {
      throw new Error(`404 ${url} — body: ${JSON.stringify(body).slice(0, 200)}`);
    }
    expect(status).toBe(200);
    const data = body as Record<string, unknown>;
    expect("last_run_at" in data).toBe(true);
    expect("next_run_at" in data).toBe(true);
    expect("cadence_minutes" in data).toBe(true);
  });

  it.skipIf(!API_BASE)("POST /api/ops/evaluate returns 200 with job_id or cooldown (no 404)", async () => {
    const { status, body, url } = await fetchPost("/api/ops/evaluate", { reason: "MANUAL_REFRESH", scope: "ALL" });
    if (status === 404) {
      throw new Error(`404 ${url} — body: ${JSON.stringify(body).slice(0, 200)}`);
    }
    expect([200, 403]).toContain(status);
    if (status === 200) {
      const data = body as Record<string, unknown>;
      expect("accepted" in data).toBe(true);
      if (data?.accepted) {
        expect(typeof data?.job_id === "string").toBe(true);
      } else {
        expect("cooldown_seconds_remaining" in data).toBe(true);
      }
    }
  });
});
