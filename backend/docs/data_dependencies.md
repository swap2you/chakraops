# Data Dependencies — Single Source of Truth (Phase 6)

This document enumerates every derived concept used in ChakraOps and defines required vs optional fields, staleness tolerance, and behavior rules. It is **authoritative** for data completeness enforcement.

**Rules:**
- If **required** missing → BLOCKED
- If **required** stale → WARN or BLOCK (per concept below)
- If **optional** missing → WARN only
- If all required present and not stale → PASS

---

## Price (Underlying)

**Provider:** ORATS (e.g. `/datav2/strikes/options` — stockPrice)

**Required fields:**
- `price` (stockPrice)

**Optional fields:**
- none

**Staleness:**
- `price` stale > 1 trading day → WARN
- `price` missing → FAIL

**Behavior:**
- Missing required → BLOCK option strategies (no sizing, no candidates)
- Stale required → WARN; do not BLOCK ranking
- Optional missing → WARN only

---

## Implied Volatility Rank (IVR)

**Provider:** ORATS (`/datav2/ivrank` — ivRank1m or ivPct1m)

**Required fields:**
- `iv_rank`

**Optional fields:**
- `iv_percentile` (if ever added)

**Staleness:**
- `iv_rank` stale > 1 trading day → WARN
- `iv_rank` missing → FAIL

**Behavior:**
- Missing required → BLOCK option strategies (regime/risk unknown)
- Stale required → WARN
- Optional missing → WARN only

---

## Option Chain Availability

**Provider:** ORATS (strikes/options)

**Required fields:**
- Availability of strikes data (non-empty response)

**Optional fields:**
- none

**Staleness:**
- Chain data stale > 1 trading day → WARN
- No chain data → FAIL

**Behavior:**
- Missing required → BLOCK option strategies; verdict HOLD or BLOCKED
- Stale required → WARN

---

## Greeks (Delta)

**Provider:** ORATS (per-strike delta from chain)

**Required fields:**
- `delta` for selected/candidate contract(s)

**Optional fields:**
- `theta`, `vega` (if used in future)

**Staleness:**
- Same as option chain (1 trading day)

**Behavior:**
- Missing delta for primary candidate → BLOCK CSP/CC ranking for that symbol
- Stale → WARN

---

## Liquidity Metrics (Bid, Ask, Volume)

**Provider:** ORATS (`/datav2/strikes/options` — bid, ask, volume)

**Required fields:**
- `bid`
- `ask`
- `volume`

**Optional fields:**
- `avg_volume` (not available from ORATS; optional everywhere)

**Staleness:**
- bid/ask/volume stale > 1 trading day → WARN
- Any required missing → FAIL

**Behavior:**
- Missing required (bid, ask, or volume) → BLOCK option strategies (REQUIRED_LIQUIDITY_FIELDS)
- Stale required → WARN
- avg_volume missing → WARN only (optional)

---

## Open Interest / Strike Volume (Options)

**Provider:** ORATS (strikes — openInt, volume per strike)

**Required fields:**
- Sufficient strike-level data to assess liquidity (OI and/or volume present)

**Optional fields:**
- none

**Staleness:**
- Same as option chain

**Behavior:**
- No valid OI/volume in strikes → liquidity_ok = False; may BLOCK or HOLD per pipeline
- Stale → WARN

---

## Earnings / Events

**Provider:** Internal or external calendar (if used)

**Required fields:**
- none (currently earnings_blocked is heuristic; no strict dependency)

**Optional fields:**
- earnings_date, event_dates

**Staleness:**
- N/A for Phase 6 (no enforcement change)

**Behavior:**
- Optional missing → WARN only
- When earnings_blocked = True → BLOCK per existing gate

---

## Risk Inputs (Position-Level)

**Provider:** Internal (user or system at entry)

**Required fields for return_on_risk:**
- `risk_amount_at_entry` (explicit 1R in dollars)

**Optional fields:**
- none

**Staleness:**
- N/A (set once at entry)

**Behavior:**
- risk_amount_at_entry missing or ≤ 0 → return_on_risk = null; outcome_tag = null; return_on_risk_status = UNKNOWN_INSUFFICIENT_RISK_DEFINITION
- Never infer R; never BLOCK exit logging

---

## Data-as-of Timestamps (Provider-Level)

**Provider:** ORATS (quoteDate from strikes/options; fetch time)

**Required fields:**
- `quote_date` or equivalent for equity/chain data

**Optional fields:**
- `fetched_at` (wall-clock fetch time)

**Staleness:**
- Computed in **trading days** from quote_date to today.
- > 1 trading day → stale (WARN per required field that depends on it)

**Behavior:**
- Expose data_as_of_orats (and data_as_of_price when distinct) in APIs
- Stale flags per required field derived from same timestamp

---

## Summary: Required vs Optional (Evaluation)

| Concept        | Required Fields              | Optional Fields | Staleness (trading days) |
|----------------|-----------------------------|-----------------|---------------------------|
| Price          | price                       | —               | > 1 → WARN; missing → FAIL |
| IVR            | iv_rank                     | iv_percentile   | > 1 → WARN; missing → FAIL |
| Option chain   | strikes available           | —               | > 1 → WARN                 |
| Delta          | delta (candidate)           | theta, vega     | > 1 → WARN                 |
| Liquidity      | bid, ask, volume            | avg_volume      | > 1 → WARN; missing → FAIL |
| OI/volume      | usable OI or volume        | —               | > 1 → WARN                 |
| risk_amount_at_entry | — (position)        | —               | N/A                        |

---

## data_sufficiency Derivation (Phase 6)

- **PASS:** required_data_missing empty AND required_data_stale empty
- **WARN:** optional_data_missing non-empty OR required_data_stale non-empty (and no required missing)
- **FAIL:** required_data_missing non-empty

Manual override: MUST NOT override when required_data_missing is non-empty. When override is applied, log distinctly (already implemented).
