# R38 — Wheel & Share Decision Engine V2 — Scope

## Purpose
Canonical Wheel lifecycle advisory V2: ownability → CSP/shares arbitration → management → assignment → CC → exit, with complete manual plans and Slack-ready payloads. Uses the R37-preserved **manual portfolio** trusted snapshot.

## Baseline
- `main` after R37 NO-GO (`ba5c505`+)
- Safety: `manual_only=true`, `trade_execution=false`, no broker writes, no scheduler enable
- No evidence-free threshold retune — reuse `profile.profit_management` (`take_profit_pct`, `roll_at_dte`)

## In scope
| ID | Deliverable |
|---|---|
| R38-W1 | Lifecycle phases + orchestrator (`evaluate_wheel_v2`) |
| R38-W2 | Manual plan (strike/expiry/DTE/delta/premium/breakeven/collateral/events/exits) |
| R38-S1 | Shares V2 staged entry + thesis failure proxies |
| R38-A1 | CSP-vs-shares arbitration with reason codes |
| R38-P1 | Portfolio-aware sizing via existing profiles / trusted snapshot |
| R38-K1 | Slack-ready render-only payload (sanitized labels) |
| API | `GET /api/ui/wheel/v2/decision?symbol=...` |
| UI | Wheel page shows V2 phase + manual plan summary |
| Wire | OPEN next_action uses management CLOSE/ROLL/HOLD (mapped) |

## Out of scope / bans
- Auto execution / broker writes
- Scheduler enablement
- Evidence-free threshold calibration (R40)
- Persisting prose into `decision_latest.json`
- Raw `FAIL_` / `WARN_` in UI-facing strings
- Enriching action-needed with wheel_v2 when risky (kept as separate endpoint)

## Reuse
`decision_engine`, `position_lifecycle_r243`, `shares_plan`, wheel `next_action`, `live_service` patterns, existing UI auth (`x-ui-key`).
