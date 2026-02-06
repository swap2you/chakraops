# Evaluation Pipeline (Implementation Reference)

This document describes the ChakraOps evaluation pipeline as implemented. It is the single source of truth for stages, inputs, outputs, failure modes, and verification paths. No aspirational behavior is documented here.

**Pipeline architecture:** The runtime uses a **2-stage evaluator** (Stage 1: stock quality + regime context; Stage 2: options chain + liquidity + contract selection). The **7 conceptual stages** below map to this implementation and to the UI (Strategy / Pipeline Details).

**References:** ORATS data flow and endpoints are documented in [ORATS_OPTION_DATA_PIPELINE.md](./ORATS_OPTION_DATA_PIPELINE.md). Field sources and null/waiver behavior are in [DATA_DICTIONARY.md](./DATA_DICTIONARY.md).

---

## Stage 1: Universe

**Purpose:** Define the set of symbols evaluated in each run. The system does not add or remove symbols automatically.

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Symbol list | `config/universe.csv` | Columns: `symbol`, `strategy_hint`, `notes`. Loaded by `app.db.universe_import` / `app.core.market.stock_universe`. |
| Strategy hint | Same file | Optional; influences CSP/CC focus. |

**Outputs**

- List of symbols passed to the evaluator (one batch per run).
- No per-symbol output at this stage.

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| Empty universe file | No symbols evaluated; run completes with zero results. | N/A (run-level). |
| Invalid symbol format | Symbol skipped; warning in logs. | N/A. |
| Duplicate entries | Deduplicated; first occurrence kept. | N/A. |

**Where to verify**

- **Config:** `chakraops/config/universe.csv`
- **API:** `GET /api/view/universe` returns symbols from persistence/cache.
- **Run JSON:** `out/evaluations/{run_id}.json` → `symbols` array length = number evaluated.

---

## Stage 2: Market Regime

**Purpose:** Global filter from index (SPY/QQQ) technicals. All symbols see the same regime. Used to cap scores and block CSP in RISK_OFF.

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Index data (SPY, QQQ) | Persisted snapshot | Close, EMA(20), EMA(50), RSI(14), ATR(14). Source: `app.core.market.market_regime`. |
| Regime persistence | `out/market/market_regime.json` | One record per trading day. |

**Outputs**

- `regime`: `RISK_ON` | `NEUTRAL` | `RISK_OFF`.
- Used in verdict resolution (e.g. RISK_OFF → HOLD, score cap 50) and in Band availability (Band A only in RISK_ON).

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| Index data unavailable | Defaults to NEUTRAL; warning in logs. | Regime still set (e.g. NEUTRAL). |
| RISK_OFF | All scores capped at 50; CSP blocked. | `REGIME_RISK_OFF` (verdict_reason_code). |
| NEUTRAL | Scores capped at 65; Band A unavailable. | Score/band in run JSON. |

**Where to verify**

- **Persistence:** `out/market/market_regime.json` → `date`, `regime`, `inputs`.
- **API:** `GET /api/market-status` → `market_phase`; evaluation run JSON → `regime`, `risk_posture`, `market_phase`.
- **Run JSON:** Top-level `regime`, `market_phase`; per-symbol `regime` in each `symbols[]` entry.

---

## Stage 3: Stock Quality (Stage 1 in code)

**Purpose:** Ensure minimum required equity data. Missing price is fatal. Missing bid/ask/volume may be waived if options liquidity is later confirmed (OPRA).

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Equity snapshot | ORATS `GET /datav2/strikes/options` (underlying tickers) | `stockPrice`→price, `bid`, `ask`, `volume`, `quoteDate`. See ORATS_OPTION_DATA_PIPELINE.md. |
| IV rank | ORATS `GET /datav2/ivrank` | `ivRank1m` or `ivPct1m` → `iv_rank`. |
| avg_volume | — | **Not available from ORATS.** Always in `missing_fields`; does not block. |

**Outputs**

- Per symbol: `price`, `bid`, `ask`, `volume`, `iv_rank`, `quote_date`, `data_sources`, `missing_fields`, `data_completeness`, `data_quality_details`.
- Stage 1 verdict: `QUALIFIED` | `HOLD` | `BLOCKED` | `ERROR`.
- `stock_verdict_reason` (string); `stage1_score` (0–100).

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| No price data | BLOCKED. | `stock_verdict_reason`: "DATA_INCOMPLETE_FATAL: No price data". |
| No equity snapshot returned | ERROR. | `stock_verdict_reason`: "No equity snapshot data returned". |
| Fatal missing fields (price or non-intraday) | HOLD. | `DATA_INCOMPLETE_FATAL` (verdict_resolver); `primary_reason` set. |
| Only intraday fields missing (bid/ask/volume), market CLOSED | Non-fatal; may proceed. | `DATA_INCOMPLETE_INTRADAY`; waiver possible in Stage 2. |
| avg_volume missing | Never blocks. | In `missing_fields`; "Not available from ORATS endpoints". |

**Where to verify**

- **Run JSON:** `symbols[].price`, `bid`, `ask`, `volume`, `missing_fields`, `data_completeness`, `data_sources`, `stage_reached` (STAGE1_ONLY if not advanced).
- **API:** `GET /api/view/evaluation/latest` → `symbols[]` same fields.
- **Code:** `app.core.eval.staged_evaluator.evaluate_stage1`, `app.core.eval.verdict_resolver.classify_data_incompleteness`.

---

## Stage 4: Strategy Eligibility (Position & Regime)

**Purpose:** Block new CSP if open CSP exists for symbol; block second CC if open CC exists. Apply regime-based blocks (e.g. no CSP in RISK_OFF).

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Open positions | Journal (SQLite / trades API) | `app.core.journal.store.list_trades`; filter `remaining_qty > 0`. |
| Current regime | Stage 2 output | RISK_ON / NEUTRAL / RISK_OFF. |
| Strategy type | Config / evaluation focus | CSP or CC. |

**Outputs**

- `position_open` (bool), `position_reason` (e.g. `POSITION_ALREADY_OPEN`).
- Verdict may be set to BLOCKED with `verdict_reason_code` = `POSITION_BLOCKED`.

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| Open CSP for symbol | New CSP BLOCKED. | `position_reason`: `POSITION_ALREADY_OPEN`; `verdict_reason_code`: `POSITION_BLOCKED`. |
| Open CC for symbol | Second CC BLOCKED. | Same. |
| RISK_OFF + CSP | BLOCKED at verdict resolution. | `REGIME_RISK_OFF`. |
| Exposure cap exceeded | BLOCKED. | `EXPOSURE_BLOCKED`. |

**Where to verify**

- **Run JSON:** `symbols[].position_open`, `position_reason`, `verdict_reason_code`; `exposure_summary`.
- **API:** `GET /api/view/positions`, `GET /api/trades` (open trades); evaluation run → `symbols[].position_reason`.
- **Code:** `app.core.eval.position_awareness`, `app.core.eval.verdict_resolver.resolve_final_verdict`.

---

## Stage 5: Options Liquidity (Stage 2 in code)

**Purpose:** Confirm usable option contracts: chain exists, and after OPRA lookup bid/ask/OI meet liquidity rules. Enables waiver of upstream stock-level bid/ask gaps when options liquidity is confirmed.

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Strike grid | ORATS `GET /datav2/strikes` or `GET /datav2/live/strikes` | Ticker param; expirations, strikes. |
| Option liquidity | ORATS `GET /datav2/strikes/options` (OCC symbols) | bidPrice, askPrice, volume, openInterest. Per ORATS_OPTION_DATA_PIPELINE.md. |

**Outputs**

- `liquidity_ok` (bool), `liquidity_reason` (string), `liquidity_grade` (e.g. A/B/C).
- `options_available`, `options_reason`.
- When OPRA confirms liquidity: `waiver_reason` = `DERIVED_FROM_OPRA`; upstream stock bid/ask gaps can be waived.

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| No options chain | HOLD/BLOCKED; no contract. | `liquidity_reason`: "No options chain data" / "No contracts meeting criteria". |
| No contracts meeting criteria (delta/DTE/liquidity) | HOLD. | `liquidity_reason` describes selection failure. |
| DATA_INCOMPLETE (chain fields missing) | HOLD. | `liquidity_reason`: "DATA_INCOMPLETE: missing ...". |
| Market CLOSED + intraday chain gaps | Non-fatal. | "DATA_INCOMPLETE_INTRADAY: ... (non-fatal, market CLOSED)". |
| OPRA confirms at least one valid put | Waiver; may set `liquidity_ok` true. | `waiver_reason`: "DERIVED_FROM_OPRA". |

**Where to verify**

- **Run JSON:** `symbols[].liquidity_ok`, `liquidity_reason`, `options_available`, `options_reason`, `waiver_reason`, `selected_contract`, `stage_reached` (STAGE2_CHAIN if passed).
- **API:** Same fields in `GET /api/view/evaluation/latest` and `GET /api/view/symbol-diagnostics`.
- **Code:** `app.core.eval.staged_evaluator.evaluate_stage2`, `app.core.options.chain_provider` (liquidity grade, selection).

---

## Stage 6: Trade Construction (Stage 2 contract selection)

**Purpose:** For symbols that passed liquidity, select the recommended contract: target delta (~-0.25 CSP), DTE window (e.g. 21–45), liquidity grade threshold.

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Options chain | Stage 2 fetch | Expirations, strikes, greeks. |
| Target delta | Config / constants | e.g. -0.25 (CSP); tolerance 0.10. |
| DTE window | Constants | e.g. TARGET_DTE_MIN=21, TARGET_DTE_MAX=45. |
| Liquidity threshold | Constants | MIN_LIQUIDITY_GRADE (e.g. B), MIN_OPEN_INTEREST (e.g. 500), MAX_SPREAD_PCT (e.g. 0.10). |

**Outputs**

- `selected_contract` (strike, expiry, delta, bid/ask, OI, liquidity_grade, selection_reason).
- `selected_expiration` (ISO date).
- `candidate_trades[]` with `strategy`, `expiry`, `strike`, `delta`, `credit_estimate`, `why_this_trade`.

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| No contracts in DTE window | ELIGIBLE possible but no specific contract. | `selected_contract` null; `liquidity_reason` or `options_reason` explains. |
| No strike near target delta | Best available selected; deviation noted. | `selection_reason` in selected_contract. |
| Liquidity below threshold | Contract not selected; HOLD. | `liquidity_reason`. |

**Where to verify**

- **Run JSON:** `symbols[].selected_contract`, `selected_expiration`, `candidate_trades`.
- **API:** `GET /api/view/symbol-diagnostics` → candidate trades and selected contract.
- **Code:** `app.core.options.contract_selector.select_contract`, `app.core.eval.staged_evaluator` (Stage 2 merge).

---

## Stage 7: Score & Band

**Purpose:** Assign a relative score (0–100) and confidence band (A/B/C) for sorting and capital hints. Score is not a probability; Band reflects data quality and regime.

**Inputs**

| Input | Source | Notes |
|-------|--------|--------|
| Prior stages | All above | Regime, data_completeness, liquidity, verdict. |
| Stage 1 score | staged_evaluator | Baseline + regime/IV/completeness. |
| Stage 2 result | Same | Liquidity and selection success. |

**Outputs**

- `score` (0–100); `confidence` (float).
- `capital_hint`: `{ band, suggested_capital_pct }` (e.g. A=5%, B=3%, C=1%).
- Verdict: `ELIGIBLE` | `HOLD` | `BLOCKED` (after verdict resolution).

**Failure modes and reason codes**

| Condition | Result | Code / UI |
|-----------|--------|-----------|
| HOLD/BLOCKED verdict | Band C. | `verdict`, `primary_reason`, `verdict_reason_code`. |
| RISK_OFF | Score capped at 50. | `score`; `regime`. |
| NEUTRAL | Score capped at 65; Band A unavailable. | Same. |
| Data incomplete (even if waived) | Score penalized; cap at 60 if severe. | `data_completeness`, `score`. |

**Where to verify**

- **Run JSON:** `symbols[].score`, `verdict`, `primary_reason`, `verdict_reason_code`, `capital_hint`, `data_completeness`.
- **API:** `GET /api/view/evaluation/latest` → `symbols[]`; counts: `eligible`, `shortlisted`, `stage1_pass`, `stage2_pass`, `holds`, `blocks`.
- **Code:** `app.core.eval.confidence_band.compute_confidence_band`, `app.core.eval.verdict_resolver.resolve_final_verdict`, `app.core.eval.staged_evaluator` (score merge).

---

## Verdict reason codes (summary)

| Code | Meaning |
|------|---------|
| `POSITION_BLOCKED` | Open position blocks new recommendation (e.g. POSITION_ALREADY_OPEN). |
| `EXPOSURE_BLOCKED` | Exposure limit exceeded. |
| `DATA_INCOMPLETE_FATAL` | Missing required EOD fields (e.g. price or options chain). |
| `REGIME_RISK_OFF` | Market regime RISK_OFF; CSP blocked. |
| `ELIGIBLE` | Passed all gates. |
| Stage 1 strings | e.g. "No price data", "Stock data complete", "Stock qualified (score: N)". |
| Stage 2 strings | e.g. "No options chain data", "DATA_INCOMPLETE: missing ...", "DERIVED_FROM_OPRA". |

---

## Run persistence

- **Directory:** `out/evaluations/` (or `get_output_dir()/evaluations`).
- **Files:** `{run_id}.json` (full run), `latest.json` (pointer to latest completed run).
- **API:** `GET /api/view/evaluation/latest`, `GET /api/view/evaluation/runs`, `GET /api/view/evaluation/{run_id}`.

See [evaluation_store.py](../app/core/eval/evaluation_store.py) and [DATA_DICTIONARY.md](./DATA_DICTIONARY.md) for field-level reference.
