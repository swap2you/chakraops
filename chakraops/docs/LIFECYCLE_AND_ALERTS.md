# Phase 2C: Lifecycle and Alerts

This document describes the lifecycle-aware alerting engine: position lifecycle states, directive alerts, cooldown behavior, and manual execution philosophy.

## Overview

The lifecycle engine monitors tracked positions and emits clear, actionable Slack alerts telling the user **what to do right now** — enter, hold, scale, exit, or abort. It never auto-executes trades; all execution is manual.

## Lifecycle States

Position lifecycle is derived from tracked positions, symbol targets, evaluation results, and regime:

| State | Description |
|-------|-------------|
| PENDING | Position planned but not yet entered |
| OPEN | Position opened, actively monitored |
| PARTIAL_EXIT | Target 1 hit; some contracts closed |
| CLOSED | Position fully closed |
| ABORTED | Regime no longer allows position |

## Lifecycle Rules

| Condition | Directive | Alert Type | Severity |
|-----------|-----------|------------|----------|
| Target 1 hit (price ≥ target1) | EXIT 1 CONTRACT | POSITION_SCALE_OUT | WARN |
| Target 2 hit (price ≥ target2) | EXIT ALL REMAINING | POSITION_EXIT | WARN |
| Stop hit (price ≤ stop) | EXIT IMMEDIATELY (STOP LOSS) | POSITION_EXIT | CRITICAL |
| Regime flips disallowed | ABORT POSITION | POSITION_ABORT | CRITICAL |
| Data health failure | HOLD — DATA UNRELIABLE | POSITION_HOLD | WARN |

## Alert Types

| Alert Type | When Emitted | Severity |
|------------|--------------|----------|
| POSITION_ENTRY | (Reserved for future entry recommendations) | INFO |
| POSITION_SCALE_OUT | Target 1 hit | WARN |
| POSITION_EXIT | Target 2 hit or stop loss | WARN / CRITICAL |
| POSITION_ABORT | Regime no longer allows | CRITICAL |
| POSITION_HOLD | Data unreliable | WARN |

## Cooldown Behavior

- **Lifecycle alerts:** Cooldown per `(position_id, action_type)`. Default: 4 hours.
- **Other alerts:** Cooldown per fingerprint. Default: 6 hours.
- Configurable in `config/alerts.yaml` via `lifecycle_cooldown_hours`.

Duplicate alerts within cooldown are suppressed and logged.

## Manual Execution Philosophy

ChakraOps **never** places trades. The lifecycle engine:

1. Evaluates positions after every evaluation run
2. Compares price (from eval snapshot) to targets (stop, target1, target2)
3. Emits Slack alerts with exact directives
4. User executes manually in their brokerage

## Slack Message Format

### ENTRY
```
🟢 ENTRY — NVDA (CSP)
Sell 170P exp 20 Feb
Premium: $4.20
Capital Used: $17,000
Action: ENTER MANUALLY
```

### SCALE OUT
```
🟡 SCALE OUT — NVDA
Target 1 hit
Action: EXIT 1 CONTRACT NOW
```

### EXIT
```
🟠 EXIT — NVDA
Target 2 hit
Action: EXIT ALL REMAINING
```

### STOP LOSS
```
🔴 STOP LOSS — NVDA
Price breached stop
Action: EXIT IMMEDIATELY
```

### ABORT
```
🚨 ABORT — NVDA
Regime no longer allowed
Action: CLOSE POSITION ASAP
```

## Persistence

- **Alerts log:** `out/alerts/alerts_log.jsonl` — all alerts (sent + suppressed)
- **Lifecycle log:** `out/lifecycle/lifecycle_log.jsonl` — lifecycle entries

Each lifecycle log entry: `position_id`, `symbol`, `lifecycle_state`, `action`, `reason`, `directive`, `triggered_at`, `eval_run_id`, `sent`.

## How to Test Locally

1. Add a tracked position (OPEN) via the Ticker page Execute (Manual).
2. Set symbol targets (stop, target1, target2) via the Targets UI or `out/symbols/{SYMBOL}_targets.json`.
3. Trigger an evaluation run (API or scheduler).
4. After the run completes, `process_run_completed` runs:
   - Evaluation alerts
   - Lifecycle evaluation for OPEN/PARTIAL_EXIT positions
   - Cooldown filter
   - Slack delivery (if configured)
   - Persistence to alerts_log and lifecycle_log
5. Check `out/lifecycle/lifecycle_log.jsonl` and Slack for directives.

### Unit Tests

```bash
python -m pytest tests/test_lifecycle_engine.py -v
```

Tests cover: Target1 scale-out, Target2 full exit, stop loss, regime abort, data failure, cooldown enforcement, no duplicate alerts.

## API Endpoints

- `GET /api/view/lifecycle-log` — Recent lifecycle log entries
- `GET /api/positions/tracked` — Tracked positions with `lifecycle_state`, `last_directive`, `last_alert_at`
