/**
 * R26.0: Map sizing constraint codes to safe display labels (no FAIL/WARN in UI).
 */

const CONSTRAINT_LABELS: Record<string, string> = {
  CASH_RESERVE: "Cash reserve",
  CASH_SECURED: "Cash secured",
  SYMBOL_CAP: "Symbol cap",
  MAX_OPTIONS_POSITIONS: "Max options positions",
  MAX_SHARES_POSITIONS: "Max shares positions",
  MAX_SYMBOLS: "Max symbols",
};

export function constraintToLabel(code: string): string {
  return CONSTRAINT_LABELS[code] ?? code;
}
