/**
 * Phase 8.5: Timestamp display — convert UTC ISO to America/New_York and label as "ET".
 * Backend stores UTC; UI displays ET.
 */

export function formatTimestampEt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }) + " ET";
  } catch {
    return String(ts ?? "—");
  }
}

export function formatTimestampEtFull(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }) + " ET";
  } catch {
    return String(ts ?? "—");
  }
}
