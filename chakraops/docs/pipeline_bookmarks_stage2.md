# Stage-2 Pipeline Bookmarks (CSP V2)

This document is the **single source of truth** for the Stage-2 option chain pipeline. It prevents regression and hallucination by defining stages, schemas, failure modes, and telemetry.

**Scope:** CSP (Cash-Secured Put) only in this phase. CC (Covered Call) will mirror this as a separate phase.

---

## Hard Rules (Non-Negotiable)

| Rule | Description |
|------|-------------|
| **R1** | CSP mode is PUT-only. If ANY CALL symbol appears in request set or response mapping → **FAIL FAST** with error `CSP_REQUEST_BUILT_CALLS` and include offending symbols. |
| **R2** | CSP is OTM-only. If ANY PUT strike >= spot_used appears in request set → **FAIL FAST** `CSP_REQUEST_INCLUDED_ITM` with the strikes and spot_used. |
| **R3** | Stage-2 must **ALWAYS** return a **FULL** stage2_trace (no "minimal fallback"). If missing → return `TRACE_MISSING_BUG`. |
| **R4** | No silent "green". Diagnostics must tell the truth: counts at each step + sample candidates + top rejection. |
| **R5** | Do NOT patch the old pipeline further. Use V2 module and route CSP to it behind a flag. |

---

## Pipeline Stages S0–S7

### S0 — Snapshot

**Purpose:** Establish spot price (required for OTM/ITM and selection).

| Item | Description |
|------|-------------|
| **Input** | Symbol; snapshot or price source (e.g. from Stage-1 / symbol snapshot service). |
| **Output** | `spot_used` (float, required). |
| **Can fail** | If no price → cannot proceed; caller must provide spot or fail earlier. |
| **Error codes** | (None; spot is required input or from trusted snapshot.) |
| **Telemetry** | `spot_used`, `snapshot_time`, `quote_as_of`. |

**Contract schema:** N/A (spot only).

---

### S1 — Expiration discovery

**Purpose:** Determine option expirations in the DTE window [30, 45].

| Item | Description |
|------|-------------|
| **Input** | Symbol, `dte_min`, `dte_max` (default 30, 45). |
| **Output** | List of expiration dates in DTE window. |
| **Can fail** | No expirations in window. |
| **Error codes** | `NO_EXPIRATIONS_IN_DTE`. |
| **Telemetry** | `dte_window` [dte_min, dte_max], `expirations_in_window` (list), `expirations_count`. |

**Contract schema:** N/A (dates only).

---

### S2 — Strike discovery (per expiry)

**Purpose:** For each expiry, call ORATS delayed strikes endpoint and extract strikes list.

| Item | Description |
|------|-------------|
| **Input** | Symbol, list of expirations, ORATS token/base. |
| **Output** | Per-expiry: list of strike prices (and raw row count). |
| **Can fail** | HTTP/parse errors (propagate; no synthetic codes here). |
| **Error codes** | (Upstream request/parse errors.) |
| **Telemetry** | `base_strikes_rows_total`, `strikes_count_per_expiry` (dict or list). |

**Contract schema:** Raw API rows; no normalized contract yet.

---

### S3 — OTM strike selection (CSP)

**Purpose:** For CSP, select PUT strikes that are OTM (strike < spot) and "near" spot.

| Item | Description |
|------|-------------|
| **Input** | Per-expiry strikes, `spot_used`, `MIN_OTM_STRIKE_PCT` (default 0.80), N (default 30). |
| **Logic** | `otm = [s for s in strikes if s < spot_used]`; `near_otm = [s for s in otm if s >= spot_used * MIN_OTM_STRIKE_PCT]`; `selected = last N` (closest below spot). |
| **Output** | Per-expiry: list of selected put strikes. |
| **Can fail** | No OTM strikes near spot. |
| **Error codes** | `CSP_NO_OTM_STRIKES_NEAR_SPOT` (include spot_used, min_otm_pct). |
| **Telemetry** | Per expiry: `selected_put_strikes` {min, max, count}, sample list. |

**Contract schema:** Strike list per expiry (no option symbol yet).

---

### S4 — Build option symbols (PUT only)

**Purpose:** Build OCC option symbols **only** for PUTs for selected strikes.

| Item | Description |
|------|-------------|
| **Input** | Symbol, per-expiry selected put strikes. |
| **Output** | List of OCC option symbols (e.g. `NVDA260320P00180000`). `puts_requested` = len; `calls_requested` MUST be 0. |
| **Can fail** | If any CALL generated → `CSP_REQUEST_BUILT_CALLS`. If any strike >= spot_used → `CSP_REQUEST_INCLUDED_ITM`. |
| **Error codes** | `CSP_REQUEST_BUILT_CALLS`, `CSP_REQUEST_INCLUDED_ITM`. |
| **Telemetry** | `puts_requested`, `calls_requested` (must be 0), `sample_request_symbols` [0:10]. |

**Contract schema:** List of strings (OCC symbols).

---

### S5 — Enrichment fetch

**Purpose:** Call ORATS delayed `strikes/options` with `tickers=<list>`.

| Item | Description |
|------|-------------|
| **Input** | List of OCC option symbols. |
| **Output** | Response rows (optionSymbol, putCall, strike, exp, delta, bid, ask, open_interest, etc.). |
| **Can fail** | HTTP/parse errors; empty response. |
| **Error codes** | (Upstream errors; empty is not necessarily a hard fail—telemetry still required.) |
| **Telemetry** | `response_rows`, `latency_ms`, `missing_field_counts` (optional). |

**Contract schema:** Raw API rows keyed by optionSymbol or list of dicts.

---

### S6 — Candidate mapping + required fields

**Purpose:** Normalize response to a canonical candidate shape; count required-field completeness.

| Item | Description |
|------|-------------|
| **Input** | Raw enrichment rows. |
| **Output** | Candidates with: `optionSymbol`, `putCall`, `strike`, `exp`, `delta`, `bid`, `ask`, `open_interest` (optional). Required for selection: strike, exp, delta, bid, ask (OI optional). |
| **Can fail** | (No hard fail; count missing.) |
| **Error codes** | (None.) |
| **Telemetry** | `puts_with_required_fields`, `missing_required_fields_counts` (for the 5 required only). |

**Contract schema (normalized candidate):**

- `optionSymbol` (str)
- `putCall` ("P" | "C")
- `strike` (float)
- `exp` (date or str)
- `delta` (float)
- `bid`, `ask` (float)
- `open_interest` (optional int)

---

### S7 — Filtering + selection

**Purpose:** Filter to PUT only, strike < spot_used, abs(delta) in [0.20, 0.40]; apply liquidity (spread_pct); select best by premium (max bid), tie-break delta near 0.30 then tighter spread.

| Item | Description |
|------|-------------|
| **Input** | Candidates from S6, `spot_used`, delta band [0.20, 0.40], spread threshold. |
| **Logic** | Filter: put only, strike < spot_used, abs(delta) in band; optional spread_pct <= threshold; OI optional (do not block on missing OI). Select: maximize bid; tie-break delta closest to 0.30 then tighter spread. |
| **Output** | `selected_contract` or null; list of top candidates for table. |
| **Can fail** | No candidate passes (not a pipeline error; report top_rejection + samples). |
| **Error codes** | (None; use top_rejection_reason + sample_rejections.) |
| **Telemetry** | `otm_puts_in_delta_band`, `delta_abs_stats` (min/median/max) for OTM puts, `rejected_counts` by reason, `sample_rejections` (10), `selected_contract` fields: symbol, exp, strike, abs_delta, bid, ask, credit_estimate, spread_pct, oi. |

**Contract schema (selected_contract):**

- symbol, exp, strike, abs_delta, bid, ask, credit_estimate, spread_pct, oi

---

## Output: contract_data (truth)

| Field | Description |
|-------|-------------|
| `available` | True if response_rows > 0 (even if no selection). |
| `selected_trade` | null or selected contract details. |
| `top_rejection_reason` | Top reason + samples if not selected. |
| `stage2_trace` | **Full** dict with all S0–S7 telemetry. Must never be null when Stage-2 ran; if missing → `TRACE_MISSING_BUG`. |

---

## Error code summary

| Code | Stage | Meaning |
|------|-------|---------|
| `NO_EXPIRATIONS_IN_DTE` | S1 | No expirations in DTE window. |
| `CSP_NO_OTM_STRIKES_NEAR_SPOT` | S3 | No OTM put strikes near spot (e.g. after min_otm_pct filter). |
| `CSP_REQUEST_BUILT_CALLS` | S4 | A CALL symbol was generated in CSP request set. |
| `CSP_REQUEST_INCLUDED_ITM` | S4 | A PUT strike >= spot_used was included in request set. |
| `TRACE_MISSING_BUG` | Output | stage2_trace was null when Stage-2 ran. |

---

## Telemetry fields required (full stage2_trace)

- **S0:** spot_used, snapshot_time, quote_as_of  
- **S1:** dte_window, expirations_in_window, expirations_count  
- **S2:** base_strikes_rows_total, strikes_count_per_expiry  
- **S3:** selected_put_strikes per expiry (min, max, count, sample)  
- **S4:** puts_requested, calls_requested, sample_request_symbols  
- **S5:** response_rows, latency_ms, missing_field_counts (optional)  
- **S6:** puts_with_required_fields, missing_required_fields_counts  
- **S7:** otm_puts_in_delta_band, delta_abs_stats, rejected_counts, sample_rejections, selected_contract (or null + top_rejection_reason)
