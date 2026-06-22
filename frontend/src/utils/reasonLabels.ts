// Copyright 2026 ChakraOps
// SPDX-License-Identifier: MIT
// R34.0: translate canonical engine reason/risk codes into safe operator labels.
// Raw FAIL_/WARN_/PASS codes must never reach rendered UI; backend already strips
// the prefixes, this is defense-in-depth plus humanization of remaining codes.

const EXACT: Record<string, string> = {
  AVAILABLE_CASH_UNKNOWN: "Available cash unknown",
  CASH_STRATEGIES_BLOCKED_PENDING_CASH_DATA: "Cash strategies paused until cash is known",
  CASH_INSUFFICIENT_FOR_ONE_CONTRACT: "Not enough cash for one contract",
  CASH_INSUFFICIENT_FOR_SHARES: "Not enough cash for shares",
  INSUFFICIENT_CASH: "Insufficient cash after buffer",
  INSUFFICIENT_SHARES: "Need 100+ shares to cover",
  INSUFFICIENT_SHARES_FOR_ONE_LOT: "Fewer than 100 shares held",
  SECTOR_DATA_UNAVAILABLE: "Sector data unavailable",
  SECTOR_BLOCKED_PENDING_DATA: "Blocked until sector is known",
  SECTOR_EXPOSURE_LIMIT_REACHED: "Sector limit reached",
  SECTOR_CAP_ENFORCED: "Sector cap applied",
  SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION: "Sector data unavailable (existing position)",
  LIQUIDITY_DATA_MISSING: "Liquidity data missing",
  LIQUIDITY_VALIDATED_UPSTREAM: "Liquidity validated",
  LOW_OPEN_INTEREST: "Low open interest",
  LOW_VOLUME: "Low volume",
  WIDE_SPREAD: "Wide bid/ask spread",
  ZERO_SIZE: "Sizes to zero",
  MISSING_PRICE: "Price unavailable",
  MISSING_CONTRACT: "Contract unavailable",
  MISSING_STRIKE: "Strike unavailable",
  MISSING_PREMIUM: "Premium unavailable",
  MISSING_DELTA: "Delta unavailable",
  MISSING_DTE: "Expiry unavailable",
  RECOMMENDATION_SET_EXCEEDS_DEPLOYABLE_CAPITAL: "Combined capital exceeds deployable cash",
  CASH_IS_FALLBACK_NOT_REQUIRED: "Cash is a fallback, not required",
  NO_ACTIONABLE_CANDIDATES: "No actionable candidates",
};

function humanize(code: string): string {
  return code
    .replace(/^(FAIL_|WARN_|PASS_)/, "")
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Translate one reason/risk code into a safe, human label. */
export function reasonLabel(code: string): string {
  if (!code) return "";
  const upper = code.toUpperCase();
  if (EXACT[upper]) return EXACT[upper];
  // Parameterized codes.
  const earn = upper.match(/^EARNINGS_BLACKOUT_(\d+)D$/);
  if (earn) return `Earnings blackout (${earn[1]}d)`;
  const regime = upper.match(/^REGIME_EXCLUDED_(.+)$/);
  if (regime) return `Regime not allowed (${humanize(regime[1])})`;
  return humanize(code);
}

/** Translate a list of codes; de-duplicate while preserving order. */
export function reasonLabels(codes?: string[] | null): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const c of codes ?? []) {
    const label = reasonLabel(c);
    if (label && !seen.has(label)) {
      seen.add(label);
      out.push(label);
    }
  }
  return out;
}
