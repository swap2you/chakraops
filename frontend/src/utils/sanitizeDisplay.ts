const FORBIDDEN_WORD = /\b(FAIL|WARN|PASS)\b/;
const FORBIDDEN_UNDERSCORE = /FAIL_|WARN_/;

/**
 * R29.4: Single UI helper for display sanitization — no raw PASS/FAIL/WARN or FAIL_/WARN_ in rendered strings.
 * Use for all integrity-check strings and any fields_diff / compare display values.
 */
export function sanitizeForDisplay(val: string | null | undefined): string {
  if (val == null) return "—";
  let s = String(val).trim();
  s = s.replace(/\bFAIL\b/gi, "—").replace(/\bWARN\b/gi, "Review").replace(/\bPASS\b/gi, "OK");
  s = s.replace(/FAIL_/g, "").replace(/WARN_/g, "");
  return s || "—";
}

/**
 * R30.4: Sanitize for readiness pack viewer; if forbidden tokens remain after sanitization, return "(redacted)".
 */
export function safeForReadinessDisplay(val: string | null | undefined): string {
  const s = sanitizeForDisplay(val);
  if (FORBIDDEN_WORD.test(s) || FORBIDDEN_UNDERSCORE.test(s)) return "(redacted)";
  return s;
}
