# ChakraOps Evaluation Field Inventory

**Generated:** Audit of computed fields during staged evaluation that are **NOT** currently exposed via `/api/ui/*`.

---

## 1. Scope

- **Inspected modules:** `app/core/evaluation/`, `app/core/eligibility/`, `app/core/ranking/`, `app/core/positions/`, `app/core/lifecycle/`, `app/core/scoring/`
- **UI endpoints:** `/api/ui/decision/*`, `/api/ui/universe`, `/api/ui/symbol-diagnostics`
- **Exposed:** Field appears in a `/api/ui/*` response and is typed in frontend `types.ts`
- **Not exposed:** Computed during evaluation but not returned by any `/api/ui/*` endpoint

---

## 2. Inventory: Fields Requested

### RSI

| Field        | Source Module                     | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|--------------|-----------------------------------|-----------------------------------|------------|-------------------------|-----------------|
| `rsi14`      | `eligibility/indicators.py`       | `eligibility_engine.run()`        | No         | No                      | Yes             |

- **Path:** `eligibility_trace.computed.RSI14` (from `build_eligibility_trace` / `computed_values`)
- **Flow:** `rsi_wilder(closes, RSI_PERIOD)` → eligibility trace
- **Used for:** CSP/CC RSI range checks (CSP_RSI_MIN/MAX, CC_RSI_MIN/MAX)
- **Note:** Full symbol diagnostics (`api_view_symbol_diagnostics`) returns `eligibility_trace`, but `/api/ui/symbol-diagnostics` strips it.

---

### ATR

| Field       | Source Module                     | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|-------------|-----------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `atr14`     | `eligibility/indicators.py`       | `eligibility_engine.run()`        | No         | No                     | Yes             |
| `atr_pct`   | `eligibility/indicators.py`       | `eligibility_engine.run()`        | No         | No                     | Yes             |

- **Path:** `eligibility_trace.computed.ATR14`, `eligibility_trace.computed.ATR_pct`
- **Flow:** `atr(highs, lows, closes, ATR_PERIOD)`, `atr_pct(highs, lows, closes, ATR_PERIOD)`
- **Used for:** ATR gate (MAX_ATR_PCT), exit_planner stop hint
- **Note:** Same as RSI — in full diagnostics only, not in UI endpoint.

---

### Regime Classification

| Field               | Source Module                     | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|---------------------|-----------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `regime` (IVR)      | `eval/staged_evaluator.py`        | Stage 1 (IVR band)                | No         | Partial (universe)     | Yes             |
| `regime` (eligibility)| `eligibility/eligibility_engine.py` | `classify_regime()` (UP/DOWN/SIDEWAYS) | No    | No                     | Yes             |
| `market_regime`     | `market/market_regime.py`         | Index-based (RISK_ON/NEUTRAL/RISK_OFF) | No     | No                     | Yes             |

- **IVR regime:** LOW_VOL | NEUTRAL | HIGH_VOL from IV rank bands
- **Eligibility regime:** UP | DOWN | SIDEWAYS from EMA alignment (daily + optional intraday)
- **Market regime:** `/api/ops/market-regime` exists but is not under `/api/ui/*`
- **Universe:** `symbols[].band` may be present from artifact; `regime` is not in UI universe DTO

---

### Support / Resistance Levels

| Field             | Source Module                   | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|-------------------|---------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `support_level`   | `eligibility/swing_cluster.py`  | `compute_support_resistance()`    | No         | No                     | Yes             |
| `resistance_level`| `eligibility/swing_cluster.py`  | `compute_support_resistance()`    | No         | No                     | Yes             |
| `distance_to_support_pct`  | `eligibility/levels.py` | `eligibility_engine.run()` | No         | No                     | Yes             |
| `distance_to_resistance_pct` | `eligibility/levels.py` | `eligibility_engine.run()` | No     | No                     | Yes             |
| `swing_high`, `swing_low` | `eligibility/levels.py`   | Pivots / swing from candles       | No         | No                     | Yes             |
| `pivots` (P, R1, S1) | `eligibility/levels.py`      | `pivot_classic()`                 | No         | No                     | Yes             |

- **Path:** `eligibility_trace.computed.support_level`, `resistance_level`, etc.
- **Used for:** Eligibility NEAR_SUPPORT/NEAR_RESISTANCE, exit_planner T1/T2/T3 and stop_hint

---

### Candidate Contract List

| Field                 | Source Module                    | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|-----------------------|----------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `selected_candidates` | `eval/staged_evaluator.py`       | Stage 2 (1–3 SelectedContract)    | No         | No                     | Yes             |
| `candidate_trades`    | `eval/staged_evaluator.py`       | Built from selected contract      | No         | No                     | Yes             |

- **Decision artifact:** `decision_snapshot.selected_signals` exposes the top signal per symbol; `decision_snapshot.candidates` is full list but not used by UI
- **Symbol diagnostics:** Full diagnostics has `candidate_trades`; `/api/ui/symbol-diagnostics` does not return it
- **Universe:** Symbols do not include full candidate list

---

### Risk Amount at Entry

| Field                | Source Module              | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|----------------------|----------------------------|-----------------------------------|------------|------------------------|-----------------|
| `risk_amount_at_entry` | `positions/models.py`    | Position record (user or system)  | No         | No                     | Yes             |

- **Exposed:** `/api/positions` (not under `/api/ui/*`)
- **Used for:** `return_on_risk`, decision quality analytics
- **Note:** Sensitive to portfolio composition; safe if scoped to user’s own positions

---

### Expected Return / Credit / Max Loss

| Field              | Source Module                      | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|--------------------|------------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `credit_estimate`  | `eval/v2_stage2_response_builder.py`, SelectedContract | Stage 2   | Yes (DecisionCandidateContract) | Yes (decision) | Yes             |
| `max_loss`         | `eval/v2_stage2_response_builder.py`, SelectedContract | Stage 2   | Yes (DecisionCandidateContract) | Yes (decision) | Yes             |
| `exit_base_target_pct` | `lifecycle/config.py`, exit_plan           | Config / trade proposal | No       | No                     | Yes             |
| `exit_extension_target_pct` | `lifecycle/config.py`           | Config / trade proposal | No       | No                     | Yes             |

- **Decision:** `selected_signals[].candidate.credit_estimate`, `candidate.max_loss` are exposed
- **Symbol diagnostics:** `candidate_trades` (with credit_estimate, max_loss) is in full diagnostics but not in UI symbol-diagnostics
- **Exit targets:** Used by Slack alerts; not in `/api/ui/*`

---

### Target Price (T1, T2, T3, Stop)

| Field             | Source Module                   | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|-------------------|---------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `structure_plan.T1`       | `lifecycle/exit_planner.py` | `build_exit_plan()`               | No         | No                     | Yes             |
| `structure_plan.T2`       | `lifecycle/exit_planner.py` | `build_exit_plan()`               | No         | No                     | Yes             |
| `structure_plan.T3`       | `lifecycle/exit_planner.py` | `build_exit_plan()`               | No         | No                     | Yes             |
| `structure_plan.stop_hint_price` | `lifecycle/exit_planner.py` | `build_exit_plan()`  | No         | No                     | Yes             |

- **Logic:** T1 = midpoint(spot, resistance/support); T2 = resistance/support; T3 = extension
- **Stop hint:** support - ATR * PANIC_ATR_MULT (CSP) or resistance + ATR * PANIC_ATR_MULT (CC)
- **Note:** Requires eligibility_trace (support/resistance, ATR); exit plan is not returned by any `/api/ui/*` endpoint

---

### Confidence Tier / Band

| Field                   | Source Module                    | Computed Where                    | In UI DTO? | Exposed via /api/ui/*? | Safe to Expose? |
|-------------------------|----------------------------------|-----------------------------------|------------|------------------------|-----------------|
| `band`                  | `eval/confidence_band.py`        | `compute_confidence_band()`       | Yes (UniverseSymbol) | Yes (universe) | Yes             |
| `suggested_capital_pct` | `eval/confidence_band.py`        | CapitalHint                       | No         | No                     | Yes             |
| `band_reason`           | `eval/confidence_band.py`        | CapitalHint                       | No         | No                     | Yes             |
| `tier` (A/B/C/NONE)     | `scoring/tiering.py`             | `assign_tier()`                   | No         | No                     | Yes             |

- **Universe:** `symbols[].band` is exposed when artifact is source
- **Symbol diagnostics:** `capital_hint` (band, suggested_capital_pct, band_reason) is in full diagnostics but not in `/api/ui/symbol-diagnostics`

---

## 3. Additional Fields Not Exposed via /api/ui/*

| Field                | Source Module                    | In UI DTO? | Safe? | Notes                                             |
|----------------------|----------------------------------|------------|-------|---------------------------------------------------|
| `score_breakdown`    | `eval/scoring.py`                | No         | Yes   | data_quality_score, regime_score, composite, etc. |
| `rank_reasons`       | `eval/scoring.py`                | No         | Yes   | reasons[], penalty                                |
| `csp_notional`       | `eval/scoring.py`                | No         | Yes   | strike * 100                                      |
| `notional_pct`       | `eval/scoring.py`                | No         | Yes   | csp_notional / account_equity                     |
| `eligibility_trace`  | `eligibility/eligibility_engine.py` | No      | Yes   | Full trace: regime, computed (RSI, ATR, S/R), rule_checks |
| `exit_plan`          | `lifecycle/exit_planner.py`      | No         | Yes   | premium_plan, structure_plan, time_plan, panic_plan |
| `stage2_trace`       | `eval/staged_evaluator.py`       | No         | Yes   | Pipeline trace, sample contracts                  |
| `contract_data`      | `eval/staged_evaluator.py`       | No         | Yes   | available, as_of, source                          |
| `contract_eligibility` | `eval/staged_evaluator.py`     | No         | Yes   | status, reasons                                   |
| `rationale`          | `eval/strategy_rationale.py`     | No         | Yes   | StrategyRationale                                 |
| `position_open`      | `eval/staged_evaluator.py`       | No         | Yes   | Boolean                                            |
| `position_reason`    | `eval/staged_evaluator.py`       | No         | Yes   | e.g. POSITION_ALREADY_OPEN                         |
| `data_completeness`  | Stage 1                          | No         | Yes   | 0.0–1.0                                            |
| `iv_rank`            | Stage 1 / ORATS                  | No         | Yes   | 0–100                                              |
| `liquidity_grade`    | Stage 2                          | No         | Yes   | A/B/C                                              |
| `selected_contract`  | Stage 2                          | No         | Yes   | Full contract; decision exposes candidate subset   |
| `option_type_counts` | Stage 2                          | No         | Yes   | puts_seen, calls_seen, unknown_seen                |
| `delta_distribution` | Stage 2                          | No         | Yes   | min/max abs put delta                              |
| `top_rejection_reasons` | Stage 2                        | No         | Yes   | Rejection reason samples                           |
| `capital_hint`       | `eval/confidence_band.py`        | No         | Yes   | band, suggested_capital_pct, band_reason           |

---

## 4. Summary

| Category              | Fields Not Exposed | Safe to Expose | Notes                                          |
|-----------------------|--------------------|----------------|------------------------------------------------|
| Technical indicators  | RSI, ATR           | Yes            | In eligibility_trace.computed                  |
| Regime                | IVR, EMA, market   | Yes            | Partial via universe; full in full diagnostics |
| Support/Resistance    | 6+ fields          | Yes            | In eligibility_trace.computed                  |
| Candidate list        | selected_candidates, candidate_trades | Yes | Full diagnostics only                          |
| Risk                  | risk_amount_at_entry | Yes          | In /api/positions only                         |
| Expected return       | credit_estimate, max_loss | Partial | Decision exposes via selected_signals          |
| Target price          | T1, T2, T3, stop   | Yes            | In exit_plan; not in UI                        |
| Confidence tier       | band, band_reason  | Partial        | band in universe; capital_hint not in UI       |
| Scoring/traces        | score_breakdown, rank_reasons, eligibility_trace | Yes | Full diagnostics only                          |

---

## 5. Recommendations

1. **Extend `/api/ui/symbol-diagnostics`**  
   Add optional `eligibility_trace` (or `computed` subset) to expose RSI, ATR, support_level, resistance_level, regime (eligibility).

2. **Expose `capital_hint`**  
   Add `capital_hint` to symbol-diagnostics UI response for band, suggested_capital_pct, band_reason.

3. **Expose `score_breakdown` and `rank_reasons`**  
   Add to symbol-diagnostics for explainability.

4. **Exit plan**  
   Consider an `/api/ui/symbol-exit-plan` or extend symbol-diagnostics with `exit_plan` (structure_plan, time_plan) when CSP/CC.

5. **Regime**  
   Expose `regime` (IVR and/or eligibility) in symbol-diagnostics and universe symbols.
