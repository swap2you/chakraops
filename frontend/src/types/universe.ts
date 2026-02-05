/**
 * Universe view from GET /api/view/universe.
 * ORATS-derived: symbol, source, last_price, fetched_at, exclusion_reason (null when success).
 */
export interface UniverseSymbolRow {
  symbol: string;
  source: string;
  last_price: number | null;
  fetched_at: string | null;
  exclusion_reason: string | null;
  /** Legacy: when present, symbol is enabled in seed universe. ORATS list has no disabled rows. */
  enabled?: boolean;
  liquidity_tier?: string | null;
  reason?: string;
}

export interface UniverseView {
  symbols: UniverseSymbolRow[];
  /** Excluded symbols (ORATS failed for these) with exclusion_reason. */
  excluded?: { symbol: string; exclusion_reason: string }[];
  updated_at: string | null;
}
