/**
 * Phase 8.6: Centralized alert classification — actionable vs non-actionable,
 * severity mapping, deduplication (avoid repeating DecisionBanner message).
 * Backend AlertsView contract unchanged; this is UI-only derivation.
 */

import type { AlertsView } from "@/types/views";

export type AlertSeverity = "info" | "warning" | "error";

/** Codes that duplicate "No trade / Capital protected" banner; exclude from dashboard. */
const NON_ACTIONABLE_CODES = new Set(["NO_TRADE"]);

/**
 * Actionable = has position_id, or (has message/code and is not NO_TRADE).
 * Dashboard shows ONLY actionable; Notifications page can show all with filter.
 */
export function isActionable(item: AlertsView["items"][0]): boolean {
  if (item.position_id) return true;
  const code = (item.code ?? "").toUpperCase();
  if (NON_ACTIONABLE_CODES.has(code)) return false;
  return !!(item.message ?? item.code);
}

/**
 * Severity from level; safe when level missing (default info).
 * Calm styling: no red flashing; subtle borders.
 */
export function severityFromLevel(level: string | undefined): AlertSeverity {
  const l = (level ?? "info").toLowerCase();
  if (l === "error") return "error";
  if (l === "warning") return "warning";
  return "info";
}

/**
 * Tailwind-style border/background for severity; safe for missing level.
 */
export function severityBorderClass(level: string | undefined): string {
  const s = severityFromLevel(level);
  if (s === "error") return "border-l-4 border-red-500/70 bg-red-500/5";
  if (s === "warning") return "border-l-4 border-amber-500/70 bg-amber-500/5";
  return "border-l-4 border-blue-500/50 bg-muted/50";
}

/**
 * Deduplicate: remove items that repeat DecisionBanner (NO_TRADE style).
 * Call with raw items; returns list safe for dashboard (actionable + deduped).
 */
export function dedupeForDashboard(items: AlertsView["items"]): AlertsView["items"] {
  return items.filter((item) => {
    const code = (item.code ?? "").toUpperCase();
    if (NON_ACTIONABLE_CODES.has(code)) return false;
    return true;
  });
}

/**
 * For dashboard: show ONLY actionable alerts, after deduplication.
 */
export function alertsForDashboard(items: AlertsView["items"]): AlertsView["items"] {
  const deduped = dedupeForDashboard(items);
  return deduped.filter(isActionable);
}
