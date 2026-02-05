/**
 * Phase 9: Market health pipeline — fetches LIVE endpoints, validates schema, outputs machine-readable report.
 * Used by GitHub Actions (.github/workflows/market-health.yml). No secrets; base URL from env LIVE_API_BASE_URL.
 * Windows-safe paths (path.join).
 */
import * as fs from "node:fs";
import * as path from "node:path";

const API_BASE = (process.env.LIVE_API_BASE_URL ?? process.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");
const TIMEOUT_MS = 15_000;
const ARTIFACTS_DIR = process.env.ARTIFACTS_DIR ?? path.join(process.cwd(), "artifacts");

type Phase = "pre" | "open" | "mid" | "post" | "unknown";

interface EndpointResult {
  path: string;
  status: number;
  ok: boolean;
  parseable: boolean;
  schemaValid: boolean;
  warnings: string[];
  durationMs: number;
}

interface Report {
  timestamp: string;
  marketPhase: Phase;
  endpointStatus: Record<string, EndpointResult>;
  validationWarnings: string[];
  executionDurationMs: number;
  success: boolean;
}

const ENDPOINTS: { path: string; requiredKeys?: string[]; arrayKeys?: string[] }[] = [
  { path: "/api/healthz" },
  {
    path: "/api/view/daily-overview",
    requiredKeys: ["date", "run_mode", "symbols_evaluated", "why_summary", "links"],
    arrayKeys: ["freeze_violation_changed_keys", "top_blockers"],
  },
  {
    path: "/api/view/positions",
    requiredKeys: [],
    arrayKeys: [],
  },
  {
    path: "/api/view/alerts",
    requiredKeys: ["as_of", "items"],
    arrayKeys: ["items"],
  },
  {
    path: "/api/view/decision-history",
    requiredKeys: [],
    arrayKeys: [],
  },
  {
    path: "/api/view/universe",
    requiredKeys: ["symbols", "updated_at"],
    arrayKeys: ["symbols"],
  },
  {
    path: "/api/view/symbol-diagnostics?symbol=SPY",
    requiredKeys: ["symbol", "fetched_at", "recommendation"],
    arrayKeys: ["gates", "blockers"],
  },
  {
    path: "/api/ops/status",
    requiredKeys: ["last_run_at", "next_run_at", "cadence_minutes", "blockers_summary"],
    arrayKeys: [],
  },
];

function derivePhase(): Phase {
  const env = process.env.MARKET_PHASE;
  if (env === "pre" || env === "open" || env === "mid" || env === "post") return env;
  const now = new Date();
  const h = now.getUTCHours();
  const m = now.getUTCMinutes();
  if (h === 13 && m >= 40) return "pre";
  if (h === 14 && m >= 30) return "open";
  if (h === 17 && m >= 25) return "mid";
  if (h >= 21 || (h >= 20 && m >= 30)) return "post";
  return "unknown";
}

function resolveUrl(p: string): string {
  return API_BASE ? `${API_BASE}${p.startsWith("/") ? p : "/" + p}` : p;
}

function validateStructure(
  body: unknown,
  requiredKeys: string[],
  arrayKeys: string[]
): { valid: boolean; warnings: string[] } {
  const warnings: string[] = [];
  if (body == null || typeof body !== "object") {
    warnings.push("Body is not an object");
    return { valid: false, warnings };
  }
  const obj = body as Record<string, unknown>;
  for (const key of requiredKeys) {
    if (!(key in obj)) {
      warnings.push(`Missing required key: ${key}`);
    }
  }
  for (const key of arrayKeys) {
    const val = obj[key];
    if (val === undefined) {
      warnings.push(`Array key '${key}' must not be undefined (can be empty [])`);
    } else if (!Array.isArray(val)) {
      warnings.push(`'${key}' must be an array`);
    }
  }
  if (Object.keys(obj).length === 0 && requiredKeys.length > 0) {
    warnings.push("Empty object where structure expected");
  }
  return { valid: warnings.length === 0, warnings };
}

async function fetchEndpoint(
  endpointPath: string,
  requiredKeys: string[],
  arrayKeys: string[]
): Promise<EndpointResult> {
  const start = Date.now();
  const url = resolveUrl(endpointPath);
  const result: EndpointResult = {
    path: endpointPath,
    status: 0,
    ok: false,
    parseable: false,
    schemaValid: false,
    warnings: [],
    durationMs: 0,
  };
  result.durationMs = Date.now() - start;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    result.durationMs = Date.now() - start;
    result.status = res.status;
    result.ok = res.ok;

    const text = await res.text();
    if (!res.ok) {
      result.warnings.push(`HTTP ${res.status}: ${text.slice(0, 200)}`);
      return result;
    }

    let body: unknown;
    try {
      body = text ? JSON.parse(text) : {};
    } catch {
      result.warnings.push("Response is not parseable JSON");
      return result;
    }
    result.parseable = true;

    if (endpointPath === "/api/view/positions" || endpointPath === "/api/view/decision-history") {
      if (!Array.isArray(body)) {
        result.warnings.push("Response must be an array (can be empty)");
        return result;
      }
      result.schemaValid = true;
      return result;
    }

    if (endpointPath === "/api/view/universe") {
      const u = body as Record<string, unknown>;
      if (!("symbols" in u) || !Array.isArray(u.symbols)) {
        result.warnings.push("Response must have symbols (array)");
        return result;
      }
      if (!("updated_at" in u)) result.warnings.push("Missing updated_at");
      result.schemaValid = result.warnings.length === 0;
      return result;
    }

    if (endpointPath.startsWith("/api/view/symbol-diagnostics")) {
      const d = body as Record<string, unknown>;
      if (!("symbol" in d) || !("fetched_at" in d)) result.warnings.push("Missing symbol or fetched_at");
      if (!("recommendation" in d)) result.warnings.push("Missing recommendation");
      result.schemaValid = result.warnings.length === 0;
      return result;
    }

    if (endpointPath === "/api/ops/status") {
      const s = body as Record<string, unknown>;
      if (!("last_run_at" in s) || !("cadence_minutes" in s) || !("blockers_summary" in s)) {
        result.warnings.push("Missing last_run_at, cadence_minutes, or blockers_summary");
      }
      result.schemaValid = result.warnings.length === 0;
      return result;
    }

    const struct = validateStructure(body, requiredKeys, arrayKeys);
    result.warnings.push(...struct.warnings);
    result.schemaValid = struct.valid;
    return result;
  } catch (e) {
    result.durationMs = Date.now() - start;
    result.warnings.push(e instanceof Error ? e.message : String(e));
    return result;
  }
}

async function main(): Promise<void> {
  if (!API_BASE) {
    console.error("LIVE_API_BASE_URL or VITE_API_BASE_URL must be set");
    process.exit(1);
  }

  const reportStart = Date.now();
  const marketPhase = derivePhase();
  const validationWarnings: string[] = [];
  const endpointStatus: Record<string, EndpointResult> = {};

  for (const ep of ENDPOINTS) {
    const result = await fetchEndpoint(
      ep.path,
      ep.requiredKeys ?? [],
      ep.arrayKeys ?? []
    );
    endpointStatus[ep.path] = result;
    if (!result.ok || !result.parseable || !result.schemaValid) {
      validationWarnings.push(
        `${ep.path}: ok=${result.ok} parseable=${result.parseable} schemaValid=${result.schemaValid} ${result.warnings.join("; ")}`
      );
    }
    if (result.warnings.length > 0 && result.durationMs >= TIMEOUT_MS - 100) {
      validationWarnings.push(`${ep.path}: possible timeout`);
    }
  }

  const executionDurationMs = Date.now() - reportStart;
  const success = validationWarnings.length === 0;

  const report: Report = {
    timestamp: new Date().toISOString(),
    marketPhase,
    endpointStatus,
    validationWarnings,
    executionDurationMs,
    success,
  };

  const now = new Date();
  const dateStr = now.toISOString().slice(0, 10);
  const timeStr = now.toISOString().slice(11, 19).replace(/:/g, "-");
  const fileName = `market_health_${dateStr}_${timeStr}.json`;
  const outDir = path.isAbsolute(ARTIFACTS_DIR) ? ARTIFACTS_DIR : path.join(process.cwd(), ARTIFACTS_DIR);
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, fileName);
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2), "utf8");
  console.log(`Report written: ${outPath}`);
  console.log(`Market phase: ${marketPhase}, success: ${success}, duration: ${executionDurationMs}ms`);
  if (!success) {
    console.error("--- FAILURE SUMMARY ---");
    validationWarnings.forEach((w) => console.error(w));
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
