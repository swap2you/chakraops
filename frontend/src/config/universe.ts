/**
 * Phase 9: Stock universe reference — mirrors backend default (symbol_universe table).
 * Backend is source of truth (chakraops DB); this is for UI display / tooltips only.
 * No execution; read-only.
 */
export type LiquidityTier = "high" | "medium" | "low";

export interface UniverseEntry {
  symbol: string;
  reason: string;
  liquidityTier: LiquidityTier;
  enabled: boolean;
}

/** Default universe (FAANG + SPY/QQQ) — matches backend chakraops/app/core/persistence.py symbol_universe init. */
export const DEFAULT_UNIVERSE: UniverseEntry[] = [
  { symbol: "AAPL", reason: "Apple Inc.", liquidityTier: "high", enabled: true },
  { symbol: "MSFT", reason: "Microsoft Corporation", liquidityTier: "high", enabled: true },
  { symbol: "GOOGL", reason: "Alphabet Inc.", liquidityTier: "high", enabled: true },
  { symbol: "AMZN", reason: "Amazon.com Inc.", liquidityTier: "high", enabled: true },
  { symbol: "META", reason: "Meta Platforms Inc.", liquidityTier: "high", enabled: true },
  { symbol: "SPY", reason: "SPDR S&P 500 ETF", liquidityTier: "high", enabled: true },
  { symbol: "QQQ", reason: "Invesco QQQ Trust", liquidityTier: "high", enabled: true },
];

export function getDefaultUniverseSymbols(): string[] {
  return DEFAULT_UNIVERSE.filter((e) => e.enabled).map((e) => e.symbol);
}
