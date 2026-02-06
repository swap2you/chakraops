# Data Dictionary (UI & API Fields)

This table documents every key field shown in the UI or returned by evaluation/API. It is implementation-truthful and aligned with [ORATS_OPTION_DATA_PIPELINE.md](./ORATS_OPTION_DATA_PIPELINE.md) and [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md).

**Conventions:**  
- **Source:** Endpoint (e.g. ORATS path), config file, or module.  
- **Null/waived:** What the UI and logic do when the value is null or when a waiver applies.  
- **Not available from provider:** Field is never populated by ORATS; fallback or waiver behavior is documented.

---

## Per-symbol evaluation (symbols[])

| Field | Meaning | Units/format | Source | Null/waived behavior | Example |
|-------|---------|--------------|--------|----------------------|--------|
| symbol | Ticker symbol | string, uppercase | universe.csv | — | "AAPL" |
| source | Data provider label | string | Evaluator | Always "ORATS" in current impl | "ORATS" |
| price | Last/current stock price | USD, float | ORATS `/datav2/strikes/options` (stockPrice) | **Fatal if null:** BLOCKED, DATA_INCOMPLETE_FATAL | 175.50 |
| bid | Underlying bid | USD, float | ORATS `/datav2/strikes/options` (bid) | Null: may be waived if options liquidity confirmed (DERIVED_FROM_OPRA); else DATA_INCOMPLETE_INTRADAY when market CLOSED | 175.48 |
| ask | Underlying ask | USD, float | ORATS `/datav2/strikes/options` (ask) | Same as bid | 175.52 |
| volume | Trading volume | integer | ORATS `/datav2/strikes/options` (volume) | Same as bid/ask; optional when CLOSED | 45230000 |
| avg_volume | Average daily volume | integer | **Not available from ORATS** | Always null; in missing_fields; does not block. UI: "N/A (not from ORATS)" | null |
| iv_rank | 1-month IV rank | 0–100, float | ORATS `/datav2/ivrank` (ivRank1m or ivPct1m) | Null: scoring/regime use fallback; not blocking | 42.5 |
| quote_date | Quote timestamp | ISO string | ORATS `/datav2/strikes/options` (quoteDate) | Null: display "N/A" | "2026-02-03T21:00:00Z" |
| verdict | Final verdict | ELIGIBLE \| HOLD \| BLOCKED \| UNKNOWN | verdict_resolver | — | "ELIGIBLE" |
| primary_reason | Human-readable reason | string | staged_evaluator, verdict_resolver | Empty if none | "Stock qualified (score: 72)" |
| verdict_reason_code | Machine reason code | string | verdict_resolver | Used for filtering/analytics | "ELIGIBLE", "POSITION_BLOCKED", "REGIME_RISK_OFF", "DATA_INCOMPLETE_FATAL" |
| confidence | Confidence value | 0–1 float | Evaluator | — | 0.85 |
| score | Relative score | 0–100 integer | staged_evaluator | Capped at 50 (RISK_OFF), 65 (NEUTRAL), 60 (data incomplete) | 72 |
| regime | Market regime (index) | RISK_ON \| NEUTRAL \| RISK_OFF | market_regime.json / evaluator | Null/unknown: treated as NEUTRAL for caps | "RISK_ON" |
| risk | Risk posture (IV-based) | BULL \| BEAR \| NEUTRAL \| UNKNOWN | Stage 1 (iv_rank) | Display only | "NEUTRAL" |
| liquidity_ok | Options liquidity passed | boolean | Stage 2 (OPRA + selection) | false → HOLD or no contract | true |
| liquidity_reason | Why liquidity pass/fail | string | Stage 2 | — | "delta=-0.24, DTE=32, OI=1200 (enhanced)" |
| options_available | Options chain evaluated | boolean | Stage 2 | false if no chain or not evaluated | true |
| options_reason | Options stage summary | string | Stage 2 | e.g. "3 expirations evaluated" | "3 expirations evaluated" |
| waiver_reason | Waiver applied | string \| null | Stage 2 | "DERIVED_FROM_OPRA" when options confirm liquidity and stock bid/ask were missing | "DERIVED_FROM_OPRA" |
| earnings_blocked | Earnings gate blocked | boolean | environment/earnings_gate | — | false |
| earnings_days | Days to next earnings | integer \| null | Event calendar | Null: not applied or N/A | 14 |
| data_completeness | Share of fields present | 0.0–1.0 float | compute_data_completeness | &lt; 0.75 → score cap 60; Band C possible | 0.85 |
| missing_fields | Fields not available | string[] | Data quality | avg_volume always included (ORATS). UI: show "N/A" for these | ["avg_volume"] |
| data_sources | Field → endpoint map | Record<string, string> | ORATS fetch | Debug/transparency | {"price":"strikes/options","iv_rank":"ivrank"} |
| data_quality_details | Field → VALID/MISSING/ERROR | Record<string, string> | Data quality | UI tooltips | {"price":"VALID","bid":"MISSING"} |
| stage_reached | Pipeline stage reached | NOT_STARTED \| STAGE1_ONLY \| STAGE2_CHAIN | staged_evaluator | — | "STAGE2_CHAIN" |
| selected_contract | Recommended contract | object (see below) | Stage 2 contract_selector | Null: ELIGIBLE possible without specific contract | { strike: 180, delta: -0.24, dte: 32, ... } |
| selected_expiration | Selected expiry | ISO date string | Stage 2 | Null if no selection | "2026-03-20" |
| candidate_trades | Suggested trades | array | Stage 2 | Empty if none | [{ strategy: "CSP", strike: 180, delta: -0.24, ... }] |
| gates | Gate pass/fail list | { name, status, reason }[] | Legacy/views | — | [] |
| blockers | Blocker strings | string[] | Evaluator | — | [] |
| position_open | Has open position (symbol) | boolean | position_awareness | — | false |
| position_reason | Why position blocks | string \| null | position_awareness | e.g. POSITION_ALREADY_OPEN | null |
| capital_hint | Band and suggested % | { band, suggested_capital_pct } | confidence_band | band: A|B|C; pct: 0.02–0.05 | { "band": "B", "suggested_capital_pct": 0.03 } |
| rationale | Strategy explanation | { summary, bullets, failed_checks, data_warnings } \| null | strategy_rationale | Optional | { summary: "...", bullets: [...] } |
| fetched_at | Evaluation timestamp | ISO string | Evaluator | — | "2026-02-03T19:01:32Z" |
| error | Error message if failed | string \| null | Evaluator | Non-null when stage error | null |

---

## selected_contract (nested)

| Field | Meaning | Units/format | Source | Null/waived behavior | Example |
|-------|---------|--------------|--------|----------------------|--------|
| contract.symbol | OCC option symbol | string | Chain provider | — | "AAPL260320P00180000" |
| contract.expiration | Expiry date | ISO string | Chain | — | "2026-03-20" |
| contract.strike | Strike price | USD, float | Chain | — | 180 |
| contract.option_type | PUT or CALL | string | Chain | — | "PUT" |
| contract.bid, ask, mid | Option bid/ask/mid | USD, float | ORATS `/datav2/strikes/options` (OCC) | Null: liquidity_ok may still be true if waiver | 2.10, 2.15, 2.125 |
| contract.open_interest | Open interest | integer | ORATS (OCC) | — | 1200 |
| contract.delta | Delta | float | ORATS (greeks) | — | -0.24 |
| contract.dte | Days to expiration | integer | Computed | — | 32 |
| contract.liquidity_grade | A/B/C/D/F | string | contract_selector | — | "B" |
| selection_reason | Why this contract | string | select_contract | — | "Best delta match in DTE window" |
| meets_all_criteria | All selection criteria met | boolean | select_contract | — | true |

---

## Run-level (evaluation run JSON / API)

| Field | Meaning | Units/format | Source | Null/waived behavior | Example |
|-------|---------|--------------|--------|----------------------|--------|
| run_id | Unique run identifier | string | evaluation_store.generate_run_id | — | "eval_20260203_190132_24cf7da8" |
| started_at | Run start | ISO string | Store | — | "2026-02-03T19:01:32Z" |
| completed_at | Run completion | ISO string \| null | Store | Null when RUNNING | "2026-02-03T19:02:15Z" |
| status | RUNNING \| COMPLETED \| FAILED | string | Store | — | "COMPLETED" |
| duration_seconds | Run duration | float | Store | — | 43.2 |
| total | Symbols in universe | integer | Run | — | 25 |
| evaluated | Symbols evaluated | integer | Run | — | 25 |
| eligible | ELIGIBLE count | integer | Run | — | 5 |
| shortlisted | Score ≥ threshold count | integer | Run | — | 8 |
| stage1_pass | Stage 1 qualified | integer | Run | — | 20 |
| stage2_pass | Stage 2 chain passed | integer | Run | — | 12 |
| holds | HOLD count | integer | Run | — | 15 |
| blocks | BLOCKED count | integer | Run | — | 5 |
| regime | Run-level regime | string \| null | market_regime | — | "RISK_ON" |
| market_phase | OPEN \| CLOSED \| etc. | string \| null | market_hours | — | "CLOSED" |
| source | manual \| scheduled \| nightly \| api | string | Trigger | — | "manual" |
| symbols | Per-symbol results | array | Evaluator | — | [] |
| exposure_summary | Open positions summary | object \| null | position_awareness | — | { total_positions: 2, ... } |
| engine | staged \| legacy | string | Run | — | "staged" |

---

## API endpoints (where fields appear)

| Endpoint | Key fields |
|----------|------------|
| GET /api/view/evaluation/latest | run_id, symbols[], counts, regime, market_phase, exposure_summary |
| GET /api/view/evaluation/{run_id} | Full run JSON (same shape as file) |
| GET /api/view/universe-evaluation | evaluation_state, symbols[], counts (in-memory cache) |
| GET /api/view/symbol-diagnostics | Per-symbol full detail + candidate_trades, selected_contract |
| GET /api/market-status | market_phase, last_market_check |
| GET /api/view/universe | symbols from config/persistence |

---

## Verification paths (summary)

- **Run JSON file:** `out/evaluations/{run_id}.json` — full run; each symbol has all per-symbol fields above.
- **Latest pointer:** `out/evaluations/latest.json` — points to latest completed run_id.
- **Market regime:** `out/market/market_regime.json` — date, regime, inputs per index.
- **Universe config:** `config/universe.csv` — symbol, strategy_hint, notes.

See [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md) for stage-by-stage "Where to verify" and reason codes.
