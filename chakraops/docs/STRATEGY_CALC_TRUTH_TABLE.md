# Strategy & Calculation Truth Table

**Single source of truth for every gate, threshold, and formula used in evaluation and scoring.**  
Generated from code scan; each row cites variable name, source field, calculation, threshold, and BLOCK/HOLD/ELIGIBLE impact.

---

## Stage 0 / Universe filter

| Variable | Source | Calculation | Threshold | Impact | Where in UI |
|----------|--------|-------------|-----------|--------|-------------|
| curated list | config/universe.csv or DB | Symbols loaded as authoritative list | — | Symbol not in list → excluded from universe | Universe view |
| allow_etfs | StockUniverseManager | Constructor default False | — | ETFs excluded unless allow_etfs=True | — |
| min_price | StockUniverseManager | Constructor default 20.0 | price < 20 → exclude | Exclude | — |
| max_price | StockUniverseManager | Constructor default 500.0 | price > 500 → exclude | Exclude | — |
| min_avg_stock_volume | StockUniverseManager | Constructor default 1_500_000 | avg_stock_volume < 1.5M → exclude | Exclude | — |
| has_options | UniverseSymbol | Per-symbol flag, default True | — | No options → exclude | — |

**Code:** `app/core/market/stock_universe.py` (StockUniverseManager), `app/api/data_health.py` (fetch_universe_from_canonical_snapshot uses get_snapshots_batch for canonical snapshot).

---

## Stage 1 gates (equity snapshot)

| Variable | Source field | Calculation | Threshold | BLOCK/HOLD/ELIGIBLE impact | Where in UI |
|----------|--------------|-------------|-----------|----------------------------|-------------|
| REQUIRED_STAGE1_FIELDS | data_requirements.py | price, bid, ask, volume, quote_date, iv_rank | Any missing → BLOCK | missing_fields non-empty → stock_verdict=BLOCKED, DATA_INCOMPLETE | Gates, symbol-diagnostics |
| STAGE1_STALE_TRADING_DAYS | data_requirements.py | = 1 | — | — | — |
| quote_date (staleness) | snapshot.quote_date | trading_days_since(quote_date_parsed) | days > STAGE1_STALE_TRADING_DAYS (1) → BLOCK | stock_verdict=BLOCKED, reason "DATA_STALE: quote_date … is N trading days old" | Stage 1 gate |
| trading_days_since | market_calendar.py | Trading days in (as_of_date, today]; US calendar | — | Used only for staleness | — |
| regime (Stage 1) | iv_rank | if iv_rank < 30 → BULL, > 70 → BEAR, else NEUTRAL | 30, 70 | No BLOCK; affects stage1_score | Stage 1 result |
| risk_posture (Stage 1) | iv_rank | iv_rank < 30 → LOW; > 70 → HIGH; else MODERATE | 30, 70 | No BLOCK | Stage 1 result |
| data_completeness | validate_equity_snapshot | From contract validator; 0.0–1.0 | < 0.75 → stage1_score capped (DATA_INCOMPLETE_SCORE_CAP) | Affects score only | — |
| stage1_score | _compute_stage1_score | Baseline 50; BULL +15, NEUTRAL +10, BEAR -5; IV 30–70 +10, IV>70 +5; × data_completeness; cap if completeness < 0.75 | DATA_INCOMPLETE_SCORE_CAP caps score | QUALIFIED when not BLOCKed | Score breakdown |
| DATA_INCOMPLETE_SCORE_CAP | staged_evaluator.py | = 60 | completeness < 0.75 → score = min(score, 60) | — | — |

**Code:** `app/core/data/data_requirements.py` (REQUIRED_STAGE1_FIELDS, STAGE1_STALE_TRADING_DAYS), `app/core/eval/staged_evaluator.py` (evaluate_stage1), `app/core/environment/market_calendar.py` (trading_days_since).

---

## Stage 2 option selection (chain / liquidity)

| Variable | Source | Calculation | Threshold | BLOCK/HOLD/ELIGIBLE impact | Where in UI |
|----------|--------|-------------|-----------|----------------------------|-------------|
| TARGET_DTE_MIN | staged_evaluator.py | = 21 | Expiration in [21, 45] DTE | Outside window → contract not selected | Chain selection |
| TARGET_DTE_MAX | staged_evaluator.py | = 45 | Same | Same | Same |
| TARGET_DELTA | staged_evaluator.py | = -0.25 (CSP put) | — | — | Same |
| DELTA_TOLERANCE | staged_evaluator.py | = 0.10 | abs(delta - TARGET_DELTA) > 0.10 (or 0.15 in OPRA path) → skip contract | Skip | Same |
| min_dte / max_dte | chain_provider / pipeline | fetch_option_chain dte_min=21, dte_max=45 (or orats_provider 7–45) | DTE window filter | No expirations in window → liquidity_ok=False | Stage 2 reason |
| LIQUIDITY_THRESHOLDS (A/B/C) | chain_provider.py | A: min_oi 1000, max_spread_pct 0.05; B: 500, 0.10; C: 100, 0.20 | OI and spread_pct vs grade | get_liquidity_grade() → A/B/C/D/F | Liquidity grade |
| spread_pct | OptionContract | (ask - bid) / mid; mid = (bid+ask)/2 | Per-grade max_spread_pct | Below threshold for grade | — |
| MIN_OPEN_INTEREST (OPRA) | staged_evaluator.py | = 500 | put.open_interest >= 500 → +20; >= 100 → +10 | Scoring only | — |
| MAX_SPREAD_PCT (OPRA) | staged_evaluator.py | = 0.10 | spread_pct <= 0.10 → +15 | Scoring only | — |
| check_opra_liquidity_gate | orats_opra / staged_evaluator | min_valid_puts=1, min_valid_contracts=1 | >= 1 valid put (bid>0, ask>0, OI>0) | Pass → liquidity_ok True | Stage 2 gate |
| Signal config (CSP/CC/IC) | SignalEngineConfig | dte_min, dte_max, min_bid, min_open_interest, max_spread_pct | dte_min ≤ DTE ≤ dte_max; bid ≥ min_bid; OI ≥ min_open_interest; spread_pct ≤ max_spread_pct | Exclude contract / no candidate | Signals engine |

**Code:** `app/core/eval/staged_evaluator.py` (TARGET_DTE_MIN/MAX, TARGET_DELTA, DELTA_TOLERANCE, MIN_OPEN_INTEREST, MAX_SPREAD_PCT, _enhance_liquidity_with_pipeline), `app/core/options/chain_provider.py` (LIQUIDITY_THRESHOLDS, get_liquidity_grade), `app/core/options/orats_chain_pipeline.py` (fetch_option_chain dte_min=21, dte_max=45), `app/signals/models.py` (SignalEngineConfig), `app/signals/csp.py` / `cc.py` / `iron_condor.py` (min_bid, min_open_interest, max_spread_pct).

---

## Scoring and banding (composite score)

| Variable | Source | Calculation | Threshold | Impact | Where in UI |
|----------|--------|-------------|-----------|--------|-------------|
| get_scoring_weights | config/scoring.yaml | data_quality, regime, options_liquidity, strategy_fit, capital_efficiency | Defaults: 0.25, 0.20, 0.20, 0.20, 0.15 (sum 1.0) | Weighted composite | Score breakdown |
| data_quality_score | scoring.py | data_completeness * 100, rounded, clamped [0,100] | — | Component 0–100 | score_breakdown.data_quality_score |
| regime_score | scoring.py | RISK_ON=100, NEUTRAL=65, RISK_OFF=50, else 50 | — | Component 0–100 | score_breakdown.regime_score |
| options_liquidity_score | scoring.py | !liquidity_ok → 20; grade A=100, B=80, C=60, else 40 | — | Component 0–100 | score_breakdown.options_liquidity_score |
| strategy_fit_score | scoring.py | ELIGIBLE & !position_open=100; ELIGIBLE & position_open=70; HOLD=50; BLOCKED/UNKNOWN=20 | — | Component 0–100 | score_breakdown.strategy_fit_score |
| capital_efficiency_score | scoring.py | 100 − penalties; notional_pct vs warn/heavy/cap; price vs high_price_penalty_above | warn_above 0.05, heavy_above 0.10, cap_above 0.20; high_price default 400 | Component 0–100; capital_penalties list | score_breakdown.capital_efficiency_score |
| composite_score | scoring.py | weighted sum of 5 components; max(0, min(100, composite)) | — | Final 0–100 | score_breakdown.composite_score, rank |
| band_a_min_score | config/scoring.yaml | Default 78 | composite >= 78 → Band A | Band | Band / rank |
| band_b_min_score | config/scoring.yaml | Default 60 | composite >= 60 → Band B | Band | Band / rank |
| notional_pct | scoring.py | csp_notional / account_equity; csp_notional = strike * 100 | warn/heavy/cap thresholds | Penalties applied | score_breakdown.notional_pct, capital_penalties |

**Code:** `app/core/eval/scoring.py` (compute_score_breakdown, data_quality_score, regime_score, options_liquidity_score, strategy_fit_score, capital_efficiency_score, get_scoring_weights, get_band_limits), `config/scoring.yaml`.

---

## Regime and risk (market regime engine)

| Variable | Source | Calculation | Threshold | Impact | Where in UI |
|----------|--------|-------------|-----------|--------|-------------|
| market_regime | market_regime.py | SPY + QQQ: EMA20, EMA50, RSI(14) | RISK_ON: EMA20 > EMA50 both and RSI ≥ 45 both; RISK_OFF: EMA20 < EMA50 either or RSI ≤ 40 either; else NEUTRAL | Regime score; execution guard (RISK_OFF blocks OPEN/ROLL) | Regime badge, execution guard |
| REGIME_INDEX_SYMBOLS | market_regime.py | ("SPY", "QQQ") | — | — | — |
| RSI (regime) | eod_snapshot / market_regime | 14-period RSI from close series | ≥ 45 for RISK_ON; ≤ 40 → RISK_OFF | See above | — |
| risk_posture (config) | settings / RiskPosture | CONSERVATIVE \| BALANCED \| AGGRESSIVE; default CONSERVATIVE | — | Trading allowed / reduced exposure in UI | Header, risk badge |
| execution_guard (market_regime) | execution_guard.py | OPEN/ROLL blocked when market_regime == RISK_OFF | — | BLOCK OPEN/ROLL | Execution guard |

**Code:** `app/core/market/market_regime.py` (_compute_regime_from_inputs, get_market_regime), `app/core/journal/eod_snapshot.py` (RSI), `app/core/execution_guard.py`, `app/core/settings.py` (risk_posture).

---

## Implemented technicals (RSI, EMA)

| Indicator | Source | Calculation | Where used |
|-----------|--------|-------------|------------|
| RSI(14) | app.core.journal.eod_snapshot, app.core.wheel | 14-period RSI from close series | market_regime (SPY/QQQ), exit_rules (CSP risk alert), wheel (RSI < 55 filter), assignment_scoring |
| EMA20 / EMA50 | eod_snapshot, market_regime | Exponential moving average | market_regime (EMA20 > EMA50 for RISK_ON), exit_rules (EMA20 < EMA50 downtrend) |

---

## NOT IMPLEMENTED — BLOCKERS (no code path)

| Item | Notes |
|------|--------|
| **MACD** | Not implemented. No MACD-based gate or signal in codebase. |
| **Bollinger Bands** | Not implemented. No Bollinger-based gate or signal in codebase. |
| **Support / Resistance levels** | Not implemented. No S/R level computation or use in evaluation. |

---

## Summary

- **Stage 0:** Universe from CSV/DB + min_price (20), max_price (500), min_avg_stock_volume (1.5M), has_options.
- **Stage 1:** Required price, bid, ask, volume, quote_date, iv_rank → BLOCK if missing; quote_date staleness > 1 trading day → BLOCK; regime/risk from iv_rank; stage1_score from baseline + regime + IV + data_completeness.
- **Stage 2:** DTE 21–45 (eval) or 7–45 (provider); delta -0.25 ± tolerance; liquidity grades A/B/C by OI and spread_pct; OPRA gate ≥ 1 valid put.
- **Scoring:** Five components (data_quality, regime, options_liquidity, strategy_fit, capital_efficiency) with weights from config; composite 0–100; bands A ≥ 78, B ≥ 60.
- **Regime:** SPY/QQQ EMA20, EMA50, RSI(14) → RISK_ON / NEUTRAL / RISK_OFF; RSI implemented; MACD, Bollinger, support/resistance not implemented.
