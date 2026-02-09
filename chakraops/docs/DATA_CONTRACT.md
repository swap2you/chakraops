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

### Liquidity (bid, ask, volume) — instrument-type-specific (Phase 8E)

**Core objective (non-negotiable):** DATA_INCOMPLETE must be emitted **only** when a field is **both** (1) required for that instrument type, and (2) missing and non-derivable. ETF/INDEX symbols must not fail due to missing bid, ask, or open_interest.

| Instrument type | Required | Optional (never cause DATA_INCOMPLETE) |
|-----------------|----------|----------------------------------------|
| **EQUITY** | `bid`, `ask`, `volume` | `avg_volume` |
| **ETF / INDEX** | `volume` only | `bid`, `ask`, `open_interest`, `avg_volume` |

- **EQUITY:** Missing `bid` or `ask` or `volume` → required missing; may BLOCK unless derivable or waived (DERIVED_FROM_OPRA).
- **ETF / INDEX (e.g. SPY, QQQ, IWM, DIA):** `bid`, `ask`, and `open_interest` are **optional**. A symbol must **never** be marked DATA_INCOMPLETE solely for missing bid/ask/open_interest for ETF/INDEX.
- Provider: ORATS `/datav2/strikes/options`. `avg_volume` is not available from ORATS; never blocks.
- When market is CLOSED, intraday gaps (bid/ask/volume) may be non-fatal and waivable in Stage 2 when options liquidity is confirmed.
- Stale → WARN. avg_volume missing → WARN only.

### Derivable fields (Phase 8E)

If a required field is derivable, it is **not** treated as missing. Derivation is explicit, logged, and surfaced in diagnostics (`field_sources`: ORATS | DERIVED | CACHED).

| Derivation | When | Effect |
|------------|------|--------|
| **mid_price** | `(bid + ask) / 2` when both exist | Used for pricing when both quotes present. |
| **synthetic_bid_ask** | When only one of bid or ask exists | The single quote is used as proxy for both; field is treated as present. |
| **open_interest** (aggregate) | From strikes/chain aggregation when available | Option-level OI aggregated; if present, satisfies chain-level OI requirements. |

- If a required field (for that instrument type) is derivable and derivation succeeds, the symbol is **not** marked DATA_INCOMPLETE for that field.
- Diagnostics must expose per-field source (ORATS | DERIVED | CACHED) in evaluation JSON and UI.

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
- For **EQUITY:** any required field missing (price, iv_rank, bid, ask, volume, quote_date, or delta for candidate) → FAIL.
- For **ETF/INDEX:** only price, iv_rank, volume, quote_date (and delta for candidate when ELIGIBLE) are required; missing bid/ask/open_interest does **not** set FAIL.

**Truth statement (Phase 8E):** DATA_INCOMPLETE is emitted only when ORATS data is missing **and** the field is non-derivable for that instrument type. For ETF/INDEX, bid, ask, and open_interest are not required; derivable fields (e.g. mid from bid+ask, synthetic bid/ask from single quote) are treated as present.

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
| Liquidity | EQUITY: bid, ask, volume; ETF/INDEX: volume only | ETF/INDEX: bid, ask, open_interest; all: avg_volume | > 1 td → WARN; missing → FAIL only for required (derivable treated as present) |
| OI/volume | usable OI or volume | — | > 1 td → WARN |
| risk_amount_at_entry | — (position-level) | — | N/A |

---

## 7. API and UI

- **GET /api/symbols/{symbol}/data-sufficiency** (or equivalent): Returns `status` (PASS | WARN | FAIL), `required_data_missing`, `optional_data_missing`, `required_data_stale`, `data_as_of_orats`, `data_as_of_price`.
- **Position detail:** Includes `data_sufficiency`, `data_sufficiency_missing_fields`, `data_sufficiency_is_override`, and the Phase 6 fields above.
- **UI:** For status WARN or FAIL, always show `missing_fields` and `required_data_missing` when non-empty. For required_data_stale non-empty, show e.g. "Data stale (last updated N trading days ago)." When is_override = true, indicate manual override and that override is invalid when required data is missing. Do not treat missing data_sufficiency as PASS; if absent, treat as FAIL.

---

## 8. ORATS Data Health (API /api/ops/data-health)

Status is **sticky** and persisted; it is not recomputed on every request.  
- **UNKNOWN:** No successful ORATS call has ever occurred.  
- **OK:** `last_success_at` within evaluation window (default 30 min).  
- **WARN:** `last_success_at` beyond window (stale).  
- **DOWN:** Last attempt failed and no success within window (or never succeeded).  
See RUNBOOK.md “ORATS data health semantics” and `app/api/data_health.py`.

---

## 9. Further Reading

- [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) — Field-level reference: every UI/API field, source, null/waived behavior, examples.
- [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) — Stage-by-stage failure modes and reason codes.
