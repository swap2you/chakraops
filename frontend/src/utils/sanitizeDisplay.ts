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
