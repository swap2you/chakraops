# R38 — Wheel & Share Decision Engine V2 — Design

## Architecture

```
evaluate_wheel_v2(symbol, context, open_position?, portfolio?, profile?)
  → evaluate_ownability (fail closed)
  → if open CSP/CC: manage_open_option → optional assignment_advisory
  → else if assigned/shares≥100: CC_ENTRY or EXIT
  → else: arbitrate_csp_vs_shares(+ optional build_shares_plan_v2)
  → build_manual_plan + to_slack_ready_payload
  → WheelDecisionV2 (manual_only=True, trade_execution=False)
```

Package: `app/core/decision_engine/wheel_v2/`

| Module | Role |
|---|---|
| `phases.py` | Lifecycle enum + safe labels |
| `contract.py` | OwnabilityResult, ManualPlan, ArbitrationResult, WheelDecisionV2 |
| `ownability.py` | Would operator want shares if assigned? |
| `management.py` | CLOSE/ROLL/HOLD via `compute_position_lifecycle` + `profit_management` |
| `assignment.py` | Next phase after assignment |
| `arbitration.py` | CSP vs shares vs cash |
| `shares_v2.py` | R23.3 plan + staged tranches + thesis_failure |
| `manual_plan.py` | Complete advisory ticket fields |
| `slack_payload.py` | Render-only Slack dict; sanitize FAIL_/WARN_ |
| `orchestrator.py` | `evaluate_wheel_v2` |

## next_action mapping (R38)

| Management action | `action_type` | Notes |
|---|---|---|
| CLOSE | HOLD | CLOSE not in ACTION_TYPES; reasons + `lifecycle_action` carry signal |
| ROLL | ROLL | Direct |
| HOLD | HOLD | Direct |

## Persistence rule
All V2 outputs are **request-time enrichment only**. Never write prose or V2 payloads into `out/decision_latest.json`.

## API
`GET /api/ui/wheel/v2/decision?symbol=X&profile=balanced` — auth via `x-ui-key` when configured. Frontend Wheel page calls this separately (not injected into action-needed).

## Stay in cash
First-class outcome when ownability fails, both strategies unattractive, or cash insufficient.
