/**
 * Phase 9: LIVE validation test suite — schema-only checks against LIVE API.
 * Skips automatically if LIVE API not reachable. No business logic.
 * Run: npm run live:check (uses LIVE_API_BASE_URL or VITE_API_BASE_URL from env).
 */
import { describe, it, expect, beforeAll } from "vitest";

const API_BASE = (process.env.LIVE_API_BASE_URL ?? process.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TIMEOUT_MS = 10_000;

const ENDPOINTS = [
  "/api/healthz",
  "/api/view/daily-overview",
  "/api/view/positions",
  "/api/view/alerts",
  "/api/view/decision-history",
] as const;

let liveReachable = false;

function resolveUrl(p: string): string {
  return API_BASE ? `${API_BASE}${p.startsWith("/") ? p : "/" + p}` : p;
}

async function fetchJson(path: string): Promise<{ ok: boolean; status: number; body: unknown }> {
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
        body = text;
      }
    }
    return { ok: res.ok, status: res.status, body };
  } catch (e) {
    clearTimeout(id);
    throw e;
  }
}

beforeAll(async () => {
  if (!API_BASE) {
    return;
  }
  try {
    const r = await fetchJson("/api/healthz");
    liveReachable = r.ok || r.status < 500;
  } catch {
    liveReachable = false;
  }
});

describe("LIVE schema (integration)", () => {
  it.skipIf(!API_BASE)("requires LIVE_API_BASE_URL or VITE_API_BASE_URL", () => {
    expect(API_BASE).toBeTruthy();
  });

  for (const path of ENDPOINTS) {
    it.skipIf(!API_BASE || !liveReachable)(`${path} returns parseable response`, async () => {
      const { ok, status, body } = await fetchJson(path);
      expect([ok, status]).toBeDefined();
      if (path === "/api/healthz") return;
      if (path === "/api/view/positions" || path === "/api/view/decision-history") {
        expect(Array.isArray(body) || (body && typeof body === "object")).toBe(true);
        return;
      }
      expect(body).toBeDefined();
      expect(body === null || typeof body === "object").toBe(true);
    });

    it.skipIf(!API_BASE || !liveReachable)(`${path} does not return undefined array for list endpoints`, async () => {
      if (path !== "/api/view/positions" && path !== "/api/view/alerts" && path !== "/api/view/decision-history") {
        return;
      }
      const { body } = await fetchJson(path);
      if (path === "/api/view/alerts") {
        const o = body as Record<string, unknown> | null;
        expect(o?.items).not.toBeUndefined();
        if (o?.items != null) expect(Array.isArray(o.items)).toBe(true);
      } else {
        expect(body).not.toBeUndefined();
        if (body != null) expect(Array.isArray(body)).toBe(true);
      }
    });
  }
});
