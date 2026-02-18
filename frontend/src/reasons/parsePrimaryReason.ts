/**
 * Parse primary_reason string into tokens and map to English via reasonDefinitions.
 * Split on ; and ,; parse key=value (e.g. rejected_due_to_delta=30 → rejected_count=30 display).
 * rejected_due_to_delta=N is a count, never displayed as delta.
 */

import { REASON_DEFINITIONS } from "./reasonDefinitions";
import type { ReasonExplained } from "@/api/types";

export interface ParsedToken {
  code: string;
  value?: number;
}

const KEY_VALUE_RE = /([a-zA-Z_][a-zA-Z0-9_]*)=(\d+)/g;
const CODE_LIKE = /^[A-Z][A-Z0-9_]+$/;

/**
 * Split primary_reason on ; and ,; parse key=value anywhere in string.
 * Examples:
 *   "No contract passed (rejected_due_to_delta=5)" → { code: "rejected_due_to_delta", value: 5 }
 *   "rejected_due_to_delta=30" → { code: "rejected_due_to_delta", value: 30 }
 *   "FAIL_RSI_RANGE; FAIL_RSL_CC" → [{ code: "FAIL_RSI_RANGE" }, { code: "FAIL_RSL_CC" }]
 */
export function parsePrimaryReason(primaryReason: string | null | undefined): ParsedToken[] {
  const raw = (primaryReason || "").trim();
  if (!raw) return [];

  const tokens: ParsedToken[] = [];
  const seen = new Set<string>();

  // Extract key=value anywhere (e.g. rejected_due_to_delta=5 inside parens)
  let m: RegExpExecArray | null;
  KEY_VALUE_RE.lastIndex = 0;
  while ((m = KEY_VALUE_RE.exec(raw)) !== null) {
    const code = m[1];
    const value = parseInt(m[2], 10);
    if (!seen.has(code)) {
      seen.add(code);
      tokens.push({ code, value });
    }
  }

  // Split on ; and , for standalone codes (FAIL_..., DATA_...)
  const parts = raw.split(/[;,]/).map((s) => s.trim()).filter(Boolean);
  for (const part of parts) {
    const eq = part.indexOf("=");
    if (eq >= 0) {
      const code = part.slice(0, eq).trim();
      const valStr = part.slice(eq + 1).trim().replace(/[()]/g, "");
      const num = /^\d+$/.test(valStr) ? parseInt(valStr, 10) : undefined;
      if (code && !seen.has(code)) {
        seen.add(code);
        tokens.push({ code, value: num });
      }
    } else if (CODE_LIKE.test(part) && !seen.has(part)) {
      seen.add(part);
      tokens.push({ code: part });
    }
  }

  return tokens;
}

/**
 * Build reasons_explained from primary_reason when backend does not provide them.
 * Uses REASON_DEFINITIONS; rejected_due_to_delta=N renders as rejected_count=N.
 */
export function buildReasonsFromPrimary(
  primaryReason: string | null | undefined
): ReasonExplained[] {
  const tokens = parsePrimaryReason(primaryReason);
  const out: ReasonExplained[] = [];

  for (const { code, value } of tokens) {
    const def = REASON_DEFINITIONS[code] ?? REASON_DEFINITIONS.OTHER;
    const message = def.template({ value });
    out.push({
      code,
      severity: def.severity,
      title: def.title,
      message,
    });
  }

  if (out.length === 0 && primaryReason?.trim()) {
    out.push({
      code: "OTHER",
      severity: "WARN",
      title: "Reason",
      message: formatGateReason(primaryReason.trim()) || "See diagnostics for details.",
    });
  }

  return out.slice(0, 10);
}

/**
 * Format raw gate/reason string for display; never show rejected_due_to_delta=N as delta.
 * Use as frontend fallback when backend may send raw codes.
 */
export function formatGateReason(raw: string | null | undefined): string {
  if (!raw || typeof raw !== "string") return "";
  const m = raw.match(/rejected_due_to_delta\s*=\s*(\d+)/i);
  if (m) return `Rejected due to delta band (rejected_count=${m[1]}).`;
  if (/FAIL_RSI_RANGE/.test(raw)) return "RSI outside preferred range";
  if (/FAIL_RSL_CC/.test(raw)) return "RSL / CC rejected";
  if (/FAIL_NOT_NEAR_SUPPORT/.test(raw)) return "Not near support";
  if (/FAIL_NO_HOLDINGS/.test(raw)) return "No shares held; covered calls disabled";
  if (/DATA_INCOMPLETE/.test(raw)) return "Required data missing";
  if (/FAIL_REGIME/.test(raw)) return "Regime conflict";
  return raw.length > 80 ? raw.slice(0, 77) + "..." : raw;
}
