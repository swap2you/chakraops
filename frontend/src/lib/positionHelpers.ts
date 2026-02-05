/**
 * Phase 7.2: Read-only derived labels for positions. No business logic.
 */
import type { PositionView } from "@/types/views";

/** Health/status: visual indicator from lifecycle + needs_attention */
export function positionHealthStatus(
  p: PositionView
): "healthy" | "attention" | "closed" {
  if (p.lifecycle_state === "CLOSED" || p.lifecycle_state === "ASSIGNED")
    return "closed";
  if (p.needs_attention || (p.attention_reasons?.length ?? 0) > 0)
    return "attention";
  return "healthy";
}

/** Next action: read-only suggestion for UI display only. S9/S10: calm copy. */
export function nextActionLabel(p: PositionView): string {
  const state = (p.lifecycle_state ?? "").toUpperCase();
  if (state === "CLOSED" || state === "ASSIGNED") return "—";
  if (p.needs_attention) {
    const reasons = p.attention_reasons ?? [];
    if (reasons.some((r) => r.includes("TARGET"))) return "Review close";
    if (reasons.some((r) => r.includes("STOP"))) return "Consider stop";
    return "Review";
  }
  const dte = p.dte ?? 999;
  if ((state === "OPEN" || state === "PARTIALLY_CLOSED") && dte <= 7) return "Consider managing";
  if (state === "OPEN" || state === "PARTIALLY_CLOSED") return "Monitor";
  return "—";
}
