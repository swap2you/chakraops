# Phase 5 Preconditions — Implemented

Phase 5 correctness requirements for decision quality.

## 1. Partial Exits / Scale-Outs

- **Model:** Multiple exit events per position (SCALE_OUT, FINAL_EXIT)
- **Storage:** `out/exits/{position_id}.json` = `{"events": [...]}`
- **Backward compat:** Single-object files migrated to events array with `event_type=FINAL_EXIT`
- **Lifecycle:** Exit discipline, time-in-trade, return metrics use full lifecycle (open → final exit)
- **Aggregated PnL:** Sum of all exit events' `realized_pnl`

## 2. R (Risk Unit) Definition

- **Explicit only:** `return_on_risk` computed only when `risk_amount_at_entry` is set on the position
- **If missing:** `return_on_risk = null`, `outcome_tag = null`, `return_on_risk_status = "UNKNOWN_INSUFFICIENT_RISK_DEFINITION"`
- **UI:** Shows "UNKNOWN (insufficient risk def.)" count in Decision Quality summary
- **No inference:** Do not approximate R from capital or other fields

## 3. Data Sufficiency

- **Auto-derived:** `derive_data_sufficiency(symbol)` uses latest evaluation run `data_completeness`
  - `>= 0.9` → PASS  
  - `>= 0.75` → WARN  
  - `< 0.75` → FAIL
- **Manual override:** `data_sufficiency_override` + `data_sufficiency_override_source` on Position
- **Logged distinctly:** Overrides written to `out/data_sufficiency_overrides.jsonl`
- **API:** `GET /api/symbols/{symbol}/data-sufficiency` returns status and `missing_fields`
