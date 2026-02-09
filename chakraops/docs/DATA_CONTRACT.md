# Data Contract — Authoritative Data Truth

This document is the single source of truth for required vs optional data, staleness rules, BLOCKED/WARN/PASS semantics, and override rules. It merges and supersedes the former data_dependencies, data_sufficiency, and the behavioral parts of the data dictionary for operator use.

**Rules (summary):**
- **Required** missing → BLOCKED (FAIL)
- **Required** stale → WARN (do not BLOCK ranking unless contract says so)
- **Optional** missing → WARN only
- All required present and not stale → PASS
- **Overrides cannot bypass required missing data.** Manual override MUST NOT override when required data is missing; the system must not present a symbol as PASS in that case.

---

## 1. Required vs Optional Data

### Price (underlying)

| Role | Fields | Provider |
|------|--------|----------|
| Required | `price` (stockPrice) | ORATS `/datav2/strikes/options` |
| Optional | — | — |

- Missing → BLOCK option strategies (no sizing, no candidates). Verdict: BLOCKED, DATA_INCOMPLETE_FATAL.
- Stale (> 1 trading day) → WARN; do not BLOCK ranking.

### Implied volatility rank (IVR)

| Role | Fields | Provider |
|------|--------|----------|
| Required | `iv_rank` | ORATS `/datav2/ivrank` (ivRank1m or ivPct1m) |
| Optional | `iv_percentile` | If ever added |

- Missing → BLOCK option strategies (regime/risk unknown).
- Stale → WARN.

### Option chain

| Role | Fields | Provider |
|------|--------|----------|
| Required | Availability of strikes data (non-empty response) | ORATS strikes/options |
| Optional | — | — |

- No chain data → BLOCK; verdict HOLD or BLOCKED.
- Chain stale > 1 trading day → WARN.

### Greeks (delta)

| Role | Fields | Provider |
|------|--------|----------|
| Required | `delta` for selected/candidate contract(s) | ORATS per-strike chain |
| Optional | `theta`, `vega` | If used in future |

- Missing delta for primary candidate → BLOCK CSP/CC ranking for that symbol.
- Stale → WARN (same as option chain, 1 trading day).

### Liquidity (bid, ask, volume)

| Role | Fields | Provider |
|------|--------|----------|
| Required | `bid`, `ask`, `volume` | ORATS `/datav2/strikes/options` |
| Optional | `avg_volume` | Not available from ORATS; never blocks |

- Any required missing → BLOCK option strategies (REQUIRED_LIQUIDITY_FIELDS), unless waived when options liquidity is confirmed (DERIVED_FROM_OPRA).
- When market is CLOSED, intraday gaps (bid/ask/volume) may be non-fatal and waivable in Stage 2 when options liquidity is confirmed.
- Stale → WARN. avg_volume missing → WARN only.

### Open interest / strike volume (options)

| Role | Fields | Provider |
|------|--------|----------|
| Required | Sufficient strike-level data to assess liquidity (OI and/or volume present) | ORATS strikes |
| Optional | — | — |

- No valid OI/volume in strikes → liquidity_ok = False; may BLOCK or HOLD per pipeline.
- Stale → WARN.

### Earnings / events

| Role | Fields | Provider |
|------|--------|----------|
| Required | none | — |
| Optional | earnings_date, event_dates | Internal or external calendar |

- Optional missing → WARN only.
- When earnings_blocked = True → BLOCK per existing gate.

### Risk inputs (position-level)

| Role | Fields | Provider |
|------|--------|----------|
| Required for return_on_risk | `risk_amount_at_entry` (explicit 1R in dollars) | Set at entry (user or system) |
| Optional | — | — |

- risk_amount_at_entry missing or ≤ 0 → return_on_risk = null; return_on_risk_status = UNKNOWN_INSUFFICIENT_RISK_DEFINITION. Never infer R; never BLOCK exit logging.

### Data-as-of timestamps

| Role | Fields | Provider |
|------|--------|----------|
| Required | `quote_date` or equivalent for equity/chain | ORATS quoteDate; fetch time |
| Optional | `fetched_at` | Wall-clock fetch time |

- Staleness is computed in **trading days** from quote_date to today. > 1 trading day → stale (WARN per required field that depends on it).
- APIs expose data_as_of_orats and data_as_of_price when distinct.

---

## 2. Staleness Rules

- **Unit:** Trading days (from quote_date to current date).
- **Threshold:** > 1 trading day → stale.
- **Effect:** Stale required data → WARN; do not BLOCK ranking unless the concept explicitly says BLOCK (e.g. no chain → BLOCK).
- **Effect:** Stale optional → WARN only.

---

## 3. BLOCKED / WARN / PASS Semantics

### Verdict and data sufficiency (evaluation)

| Term | Meaning |
|------|---------|
| **BLOCKED** | System refuses to recommend. A reason is always provided (e.g. required_data_missing, REGIME_RISK_OFF, POSITION_BLOCKED). Do not override without explicitly accepting risk. |
| **HOLD** | Symbol did not pass all gates (e.g. data incomplete, liquidity insufficient, regime not favorable, position open). No recommendation right now. |
| **ELIGIBLE** | Passed all gates; candidate for trade. |
| **UNKNOWN** | Not enough information (e.g. return_on_risk when risk_amount_at_entry not set). Treat as non-actionable; do not infer. |

### Data sufficiency status (structural)

| Status | Meaning |
|--------|---------|
| **PASS** | `required_data_missing` empty AND `required_data_stale` empty. |
| **WARN** | `optional_data_missing` non-empty OR `required_data_stale` non-empty (and no required missing). |
| **FAIL** | `required_data_missing` non-empty. |

No decision may appear PASS when required data is missing or when the symbol has not been evaluated.

**When FAIL is set:**
- No evaluation data → FAIL, required_data_missing = ["no_evaluation_data"].
- Symbol not in latest evaluation → FAIL, required_data_missing = ["symbol_not_in_latest_evaluation"].
- Any required field missing (price, iv_rank, bid, ask, volume, or delta for candidate) → FAIL.

---

## 4. Override Rules

- **Manual override:** When `data_sufficiency_override` is set on a position, it is logged as MANUAL.
- **MUST NOT override when:** `required_data_missing` is non-empty. Override is invalid in that case; system must not present the symbol as PASS.
- **Override applies only** when the operator explicitly sets an override for WARN/edge cases; it never clears FAIL due to required missing.

---

## 5. Waivers (stock-level bid/ask/volume)

When **options liquidity is confirmed** (Stage 2: OPRA/chain has usable bid/ask/OI for the symbol), the pipeline may **waive** upstream stock-level bid/ask/volume gaps. In that case:

- `waiver_reason` = "DERIVED_FROM_OPRA".
- Stock-level missing bid/ask/volume do not cause BLOCK for that symbol.
- This applies when market is CLOSED and intraday fields would otherwise be missing; the system does not infer optional data as present without a waiver reason.

---

## 6. Summary Table (evaluation)

| Concept | Required fields | Optional fields | Staleness |
|---------|-----------------|-----------------|-----------|
| Price | price | — | > 1 td → WARN; missing → FAIL |
| IVR | iv_rank | iv_percentile | > 1 td → WARN; missing → FAIL |
| Option chain | strikes available | — | > 1 td → WARN; missing → BLOCK |
| Delta | delta (candidate) | theta, vega | > 1 td → WARN |
| Liquidity | bid, ask, volume | avg_volume | > 1 td → WARN; missing → FAIL (or waive per contract) |
| OI/volume | usable OI or volume | — | > 1 td → WARN |
| risk_amount_at_entry | — (position-level) | — | N/A |

---

## 7. API and UI

- **GET /api/symbols/{symbol}/data-sufficiency** (or equivalent): Returns `status` (PASS | WARN | FAIL), `required_data_missing`, `optional_data_missing`, `required_data_stale`, `data_as_of_orats`, `data_as_of_price`.
- **Position detail:** Includes `data_sufficiency`, `data_sufficiency_missing_fields`, `data_sufficiency_is_override`, and the Phase 6 fields above.
- **UI:** For status WARN or FAIL, always show `missing_fields` and `required_data_missing` when non-empty. For required_data_stale non-empty, show e.g. "Data stale (last updated N trading days ago)." When is_override = true, indicate manual override and that override is invalid when required data is missing. Do not treat missing data_sufficiency as PASS; if absent, treat as FAIL.

---

## 8. Further Reading

- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) — Field-level reference: every UI/API field, source, null/waived behavior, examples.
- [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) — Stage-by-stage failure modes and reason codes.
