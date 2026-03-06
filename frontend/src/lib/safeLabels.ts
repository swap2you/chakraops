/**
 * R24.6: Safe display labels for gate/status — UI must never show literal "FAIL" or "WARN".
 * Use this helper everywhere we render status to the user.
 */
const SAFE_LABELS: Record<string, string> = {
  PASS: "Passed",
  FAIL: "Blocked",
  WARN: "Degraded",
  OK: "OK",
  SKIP: "Skipped",
  HOLD: "Hold",
  BLOCKED: "Blocked",
  ELIGIBLE: "Eligible",
  NOT_RUN: "Not run",
};

/**
 * Returns a safe label for gate/status for display. Never returns "FAIL" or "WARN".
 */
export function gateStatusToLabel(status: string | null | undefined): string {
  if (status == null || status === "") return "—";
  const s = status.trim().toUpperCase();
  return SAFE_LABELS[s] ?? status;
}

/** R24.6/R28.3: Sanitize message text for display so UI never shows literal FAIL/WARN/PASS. */
export function sanitizeMessageForDisplay(msg: string | null | undefined): string {
  if (msg == null || msg === "") return "—";
  return msg
    .replace(/\bFAIL\b/g, "Blocked")
    .replace(/\bWARN\b/g, "Degraded")
    .replace(/\bPASS\b/g, "OK");
}
