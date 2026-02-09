# Exits — Field Reference

Phase 4/5: Manual exit logging. Multiple events per position (SCALE_OUT, FINAL_EXIT).

## Event Types

| Value | Meaning | Position Status After |
|-------|---------|------------------------|
| SCALE_OUT | Partial exit (e.g. 1 of 2 contracts) | PARTIAL_EXIT |
| FINAL_EXIT | Position fully closed | CLOSED |

## Guardrail: SCALE_OUT without FINAL_EXIT

If a position has SCALE_OUT events but no FINAL_EXIT:

- Position status must be PARTIAL_EXIT, not CLOSED.
- Position is excluded from decision quality (full lifecycle open → final exit not complete).

## Exit Reasons (LOCKED ENUM)

TARGET1, TARGET2, STOP_LOSS, ABORT_REGIME, ABORT_DATA, MANUAL_EARLY, EXPIRY, ROLL

## Storage

- `out/exits/{position_id}.json` = `{"events": [...]}`
- Backward compat: Single-object files migrated to events array with event_type=FINAL_EXIT.

## Aggregated PnL

For decision quality, `realized_pnl` = sum of all exit events' realized_pnl.

## Time in Trade

Computed from `opened_at` → final exit's `exit_date`. Only FINAL_EXIT defines the end of the lifecycle.

## API Response (Position Detail)

| Field | Meaning | When UNKNOWN |
|-------|---------|--------------|
| `exit` | Single final exit (or last event) | null when no exits |
| `exit_events` | All exit events (SCALE_OUT + FINAL_EXIT) | [] when none |
| `return_on_risk` | See decision_quality.md | null when risk_amount_at_entry missing |
| `return_on_risk_status` | KNOWN \| UNKNOWN_INSUFFICIENT_RISK_DEFINITION | Always present when exit exists |
| `outcome_tag` | WIN \| SCRATCH \| LOSS | null when R unknown |

## UI Interpretation

- **exit_events has only SCALE_OUT:** Position is PARTIAL_EXIT; do not show as closed.
- **return_on_risk is null:** Show UNKNOWN (insufficient risk definition), not a number.
- **return_on_risk_status:** Use to decide whether to show outcome_tag or UNKNOWN.
