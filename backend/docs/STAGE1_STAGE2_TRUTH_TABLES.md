# ChakraOps Repo Audit: Stage-1 + Stage-2 Truth Tables

## SECTION A — Stage-1 Data Pipeline

### ORATS Endpoints Used (Grouped by Purpose)

| Purpose | Endpoint | Client Function | File | Cache TTL Policy |
|---------|----------|-----------------|------|------------------|
| **Core snapshot/quote** | `GET /datav2/cores` | `fetch_core_snapshot()` | `orats/orats_core_client.py` | `cores`: 60s |
| **Core snapshot/quote** | `GET /datav2/strikes/options` (underlying tickers) | `fetch_equity_quotes_batch()` → `_fetch_equity_quotes_single_batch()` | `orats/orats_equity_quote.py` | `quotes`: 60s |
| **IV Rank** | `GET /datav2/ivrank` | `fetch_iv_ranks_batch()` → `_fetch_iv_ranks_single_batch()` | `orats/orats_equity_quote.py` | `iv_rank`: 6h |
| **Strikes/chain** | `GET /datav2/strikes` | `OratsDelayedClient.get_strikes()` | `orats/orats_opra.py` | `strikes`: 60s |
| **Strikes/chain** | `GET /datav2/strikes/options` (OCC symbols) | `OratsDelayedClient.get_strikes_by_opra()` | `orats/orats_opra.py` | `strikes`: 60s |
| **Hist dailies (derived)** | `GET /datav2/hist/dailies` | `derive_avg_stock_volume_20d()` | `orats/orats_core_client.py` | In-memory per ticker/day |
| **Calendar/earnings** | — | *(cache_policy defines `calendar`, `earnings` 24h but no caller found)* | — | 24h (defined only) |

### Canonical Snapshot Composition

**`app/core/data/symbol_snapshot_service.py` — `get_snapshot()`**

| Source | Fields Consumed | Downstream Use |
|--------|-----------------|----------------|
| `fetch_full_equity_snapshots` (strikes/options + ivrank) | `price`, `bid`, `ask`, `volume`, `quote_date`, `iv_rank` | Stage-1 validation, data completeness |
| `fetch_core_snapshot` | `stkVolu`, `avgOptVolu20d` | Volume metrics |
| `derive_avg_stock_volume_20d` (hist/dailies) | `stockVolume` → mean 20d | `avg_stock_volume_20d` |

### Fields Consumed Downstream (Stage-1)

| Field | Required? | Source | If Missing |
|-------|-----------|--------|------------|
| `price` | ✅ | strikes/options | BLOCK (DATA_INCOMPLETE) |
| `bid` | ✅ | strikes/options | BLOCK |
| `ask` | ✅ | strikes/options | BLOCK |
| `volume` | ✅ | strikes/options | BLOCK |
| `quote_date` | ✅ | strikes/options | BLOCK |
| `iv_rank` | ✅ | ivrank | BLOCK |
| `avg_option_volume_20d` | ❌ | cores | Informational |
| `avg_stock_volume_20d` | ❌ | hist/dailies | Informational |

### Phase 6 Data Dependencies Behavior

| Condition | Status | Action |
|-----------|--------|--------|
| `required_data_missing` non-empty | FAIL | BLOCK |
| `required_data_stale` non-empty | WARN | BLOCK (Stage-1 hard gate) |
| `optional_data_missing` non-empty | WARN | No BLOCK |
| All required present + not stale | PASS | Proceed |

---

## SECTION B — Health Gate / Data Sufficiency

### Required vs Optional Fields (Source of Truth)

**Module:** `app/core/symbols/data_dependencies.py`, `app/core/data/data_requirements.py`

| Type | Fields |
|------|--------|
| **Required (EQUITY)** | `price`, `iv_rank`, `bid`, `ask`, `volume`, `quote_date` |
| **Required (ETF/INDEX)** | `price`, `iv_rank`, `volume`, `quote_date` |
| **Optional** | *(none that block)* |

### Staleness Computation

- **Source:** `app/core/environment/market_calendar.py` — `trading_days_since(as_of_date)`
- **Threshold:** `STAGE1_STALE_TRADING_DAYS = 1` (`data_requirements.py`)
- **Logic:** `quote_date` → parse to `date` → `trading_days_since()` → if `> 1` → stale
- **BLOCK trigger:** `required_data_stale` non-empty OR `days > STAGE1_STALE_TRADING_DAYS`
- **WARN trigger:** `required_data_stale` non-empty with no required missing (per `dependency_status`)

### Where Enforced

| Location | Gate |
|----------|------|
| `staged_evaluator.evaluate_stage1()` | Required missing → BLOCK |
| `staged_evaluator.evaluate_stage1()` | Stale (quote_date > 1 trading day) → BLOCK |
| `universe_quality_gates.evaluate_universe_quality()` | Phase 9.0: pre-chain gate (data_sufficiency) |

---

## SECTION C — Stage-2 Selection + Eligibility + Ranking

### Contract Selection Rules (CSP)

| Rule | Source | Threshold |
|------|--------|-----------|
| Option type | `chain_provider`, `staged_evaluator` | PUT only (CSP) |
| DTE | `wheel_strategy_config` | 30–45 |
| Delta | `TARGET_DELTA_RANGE` | |delta| 0.20–0.40 |
| OTM | `staged_evaluator` | strike < spot |
| Required chain fields | `REQUIRED_CHAIN_FIELDS` | strike, expiration, bid, ask, delta, open_interest |
| Min OI | `WHEEL_CONFIG[MIN_OPTION_OI]` | 500 |
| Max spread % | `MAX_SPREAD_PCT` (wheel) | 2% (V2); 10% (config) |
| Liquidity grade | `ContractLiquidityGrade` | Min B (OI≥500, spread≤10%) |

### Eligibility Failure Reasons

| Code / Reason | When |
|---------------|------|
| `DATA_INCOMPLETE` | Required Stage-1 fields missing |
| `DATA_STALE` | quote_date > 1 trading day |
| `OPTION_CHAIN_MISSING_FIELDS` | Chain missing required fields (strike, expiration, bid, ask, delta, open_interest) |
| `No suitable contract found` | No contract passed selection |
| `No OTM puts` | All puts ITM |
| `No contracts in 30–45 DTE range` | No PUTs in DTE band |
| `rejected_due_to_delta` | Delta outside 0.20–0.40 |
| `rejected_due_to_oi` | OI < 500 |
| `rejected_due_to_spread` | Spread > threshold |
| `rejected_due_to_missing_fields` | bid/ask/delta missing |
| `rejected_due_to_itm` | strike ≥ spot |
| `Blocked by market regime: RISK_OFF` | Regime gate |
| `Stage 2 error: ...` | Exception during Stage-2 chain fetch or selection |

### Scoring Formula

**Module:** `app/core/eval/scoring.py` — `compute_score_breakdown()`

| Component | Weight (default) | Input | Score Range |
|-----------|------------------|-------|-------------|
| data_quality | 0.25 | data_completeness | 0–100 |
| regime | 0.20 | regime string | LOW_VOL=40, NEUTRAL=65, HIGH_VOL=85 |
| options_liquidity | 0.20 | liquidity_ok, grade | A=100, B=80, C=60, fail=20 |
| strategy_fit | 0.20 | verdict, position_open | ELIGIBLE=100, HOLD=50, BLOCKED=20 |
| capital_efficiency | 0.15 | notional_pct vs thresholds | 100 − penalties (warn/heavy/cap) |

**Composite:** `Σ (component × weight)` → 0–100. Regime cap applied in caller.

### Band Logic

**Module:** `app/core/eval/confidence_band.py` — `compute_confidence_band()`

| Band | Conditions |
|------|------------|
| **A** | ELIGIBLE, score ≥ 78, RISK_ON, data_completeness ≥ 0.75, liquidity_ok, no position_open, completeness ≥ 0.9 |
| **B** | ELIGIBLE, score ≥ 60, any gate not meeting A |
| **C** | HOLD/BLOCKED, or score < 60, or data_completeness < 0.75 |

**Capital hints:** A=5%, B=3%, C=2% of portfolio.

### Final Ranking Sort Precedence

- **Stage-1 → Stage-2:** `qualified.sort(key=stage1_score, reverse=True)`; top K (STAGE1_TOP_K, e.g. 20) advance.
- **Top eligible / holds:** `sorted(..., key=lambda x: x["score"], reverse=True)[:10]`
- **Contract selection:** `passed.sort(key=rank_key, reverse=True)` — premium, delta fit, liquidity

### Pseudo Examples

**ELIGIBLE case:** AAPL — price $175, iv_rank 65 (HIGH_VOL), bid/ask/volume/quote_date present, quote_date today → Stage-1 QUALIFIED. Stage-2: chain with OTM PUTs in 30–45 DTE, delta 0.25, OI 1200, spread 3% → contract selected → ELIGIBLE.

**FAIL case:** XYZ — price $5 (below min) → universe gate SKIP.  
**FAIL case:** ABC — price $100, iv_rank 10 (LOW_VOL), quote_date 3 trading days ago → Stage-1 BLOCKED (DATA_STALE).

---

## SECTION D — Outputs & Surfaces

### Slack SIGNAL Payload (from `slack_dispatcher._fmt_signal`)

| Field | Notes |
|-------|-------|
| symbol | |
| mode / mode_decision | CSP, CC |
| tier | |
| severity | |
| composite_score | |
| strike, dte, delta | |
| capital_required_estimate | |
| guardrail_adjusted_msg | Optional |
| exit_base_target_pct, exit_extension_target_pct, exit_T1, exit_T2 | |

### Slack DAILY Summary (from `slack_dispatcher._fmt_daily`)

| Field | Notes |
|-------|-------|
| top_signals | Top 5 (symbol, tier, severity) |
| open_positions_count | |
| total_capital_used | |
| exposure_pct | |
| average_premium_capture | |
| exit_alerts_today | |
| portfolio_risk_summary | Optional section |

### Nightly Slack (from `nightly_evaluation.build_slack_message`)

| Field | Notes |
|-------|-------|
| run_id, timestamp | |
| regime, risk_posture, duration | |
| universe_total, evaluated, stage1_pass, stage2_pass | |
| eligible, holds, blocks | |
| cache_hit_rate_pct, requests_estimated, top_endpoint_hit_rate | |
| gate_skips_count, gate_skip_reasons_summary | |
| top_eligible (symbol, score, strike, expiration, delta, bid) | |
| top_holds (symbol, primary_reason) | |

### UI Universe Page (`/api/view/universe`)

- **Source:** `fetch_universe_from_canonical_snapshot` (live) or `build_universe_from_latest_artifact` (artifact)
- **Fields:** `symbols[]` with SymbolSnapshot fields; `excluded`, `updated_at`, `source`, `as_of`, `run_id`

### Portfolio Command Center (`/api/portfolio/*`, `/api/dashboard/opportunities`)

- Uses evaluation run data, `verdict`, `primary_reason`, `score`, `selected_contract`, `capital_hint`, etc.

### Inconsistent Naming to Normalize

| Backend | UI / API alias |
|---------|----------------|
| `verdict` | Legacy; `final_verdict` preferred |
| `primary_reason` | Same |
| `composite_score` vs `score` | Both used |
| `expiration` vs `expir_date` | Varies by context |
| `strike` vs `strike_price` | Strike preferred |
| `bid` / `ask` | Sometimes nested in `contract` |

---

## SECTION E — Recommendations (No Logic Changes)

1. **Verdict field:** Standardize on `final_verdict` in API responses; deprecate `verdict` or document as legacy alias.
2. **Score field:** Use `score` as canonical; avoid `composite_score` in UI contracts.
3. **Contract nesting:** Use `selected_contract.contract.strike` consistently; document schema in OpenAPI/contract.
4. **Date fields:** Use `quote_date` and `expiration` (ISO) consistently; avoid `expir_date` / `expiry` mix.
5. **Band display:** Expose `band`, `suggested_capital_pct`, `band_reason` from `capital_hint` in all opportunity views.
6. **Reason codes:** Add `verdict_reason_code` (e.g. `DATA_INCOMPLETE`, `REGIME_RISK_OFF`) to all verdict-bearing payloads for UI filtering.
7. **Missing-field lists:** Always include `missing_fields` or `required_data_missing` when status is FAIL/WARN for diagnostics.
8. **Slack vs API:** Align Slack field names with API keys where possible (e.g. `composite_score` → `score`).
9. **Source provenance:** Include `source` (e.g. `LIVE_COMPUTE`, `ARTIFACT_LATEST`) in universe/evaluation responses for debugging.
10. **Cache TTL keys:** Document `cache_policy` keys (`cores`, `strikes`, `quotes`, `iv_rank`) in API/ops docs for operators.
