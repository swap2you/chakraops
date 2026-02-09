# Decision Quality — Field Reference (Phase 4/5/6)

Phase 4/5: Post-trade decision quality analysis. All fields are computed on load; none are stored.

## UNKNOWN vs BLOCKED vs WARN

| Term | Meaning | When |
|------|---------|------|
| **UNKNOWN** | The system does not have enough information to compute or tag. Never infer. | e.g. `return_on_risk` when `risk_amount_at_entry` missing; data sufficiency when symbol not in run. |
| **BLOCKED** | The system explicitly refuses to recommend (e.g. required data missing, risk limits exceeded). | Phase 6: `required_data_missing` non-empty → risk_status BLOCKED. Portfolio limits can also BLOCK. |
| **WARN** | Proceed with caution; optional data missing or data stale. | e.g. `required_data_stale` or `optional_data_missing`; nearing capital utilization. |

## Outcome Summary (GET /api/decision-quality/summary)

| Field | Meaning | When Computed | When UNKNOWN |
|-------|---------|---------------|--------------|
| `status` | OK \| INSUFFICIENT DATA \| ERROR | On request | — |
| `win_count` | Count of outcomes tagged WIN | From positions with FINAL_EXIT + risk_amount_at_entry | — |
| `scratch_count` | Count of outcomes tagged SCRATCH | Same | — |
| `loss_count` | Count of outcomes tagged LOSS | Same | — |
| `unknown_risk_definition_count` | Count where return_on_risk is null (no R) | When risk_amount_at_entry missing/≤0 | Always present |
| `avg_time_in_trade_days` | Avg days open → final exit | From FINAL_EXIT positions | null when INSUFFICIENT DATA |
| `avg_capital_days_used` | Avg capital × days | Same | null when INSUFFICIENT DATA |
| `total_closed` | Positions with FINAL_EXIT | Always | — |

## return_on_risk and outcome_tag

| Field | Meaning | When Computed | When UNKNOWN |
|-------|---------|---------------|--------------|
| `return_on_risk` | realized_pnl / risk_amount (R) | Only when risk_amount_at_entry > 0 | null when risk_amount_at_entry missing or ≤ 0 |
| `return_on_risk_status` | KNOWN \| UNKNOWN_INSUFFICIENT_RISK_DEFINITION | Always | UNKNOWN_INSUFFICIENT_RISK_DEFINITION when return_on_risk is null |
| `outcome_tag` | WIN \| SCRATCH \| LOSS | Only when return_on_risk is known | null when R unknown |

### Outcome Rules (when R known)

- **WIN:** return_on_risk ≥ 0.5
- **SCRATCH:** −0.2 < return_on_risk < 0.5
- **LOSS:** return_on_risk ≤ −0.2

## UI Interpretation

- **return_on_risk is null:** Do not treat as valid. Show "UNKNOWN (insufficient risk definition)".
- **return_on_risk_status = UNKNOWN_INSUFFICIENT_RISK_DEFINITION:** UI must not infer a numeric R. Show explicit UNKNOWN state.
- **unknown_risk_definition_count > 0:** Count of closed positions that could not be tagged because R was not defined.
- **INSUFFICIENT DATA:** Fewer than 30 closed positions. Show INSUFFICIENT DATA, not zeroes.
