# Current State — ChakraOps

_Last updated: 2026-08-10 — R40.1 **FINAL_ACCEPTANCE_HOLD**_

## Release Status

| Field | Value |
|-------|-------|
| Program | R36.3–R40 **FINAL_ACCEPTANCE_HOLD** (not COMPLETE) |
| Honesty (R40 backtest) | `TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP` |
| Current branch | `main` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Requirements | `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md` |
| Daily runbook | `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md` |
| R40.1 acceptance | `docs/ai/releases/R40.1/R40_1_ACCEPTANCE.md` |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. Robinhood sync = **NO_GO** (manual portfolio). ORATS sole options provider. Scheduler disabled (fail-closed). Stay in cash is valid.

## Deferred / gaps

- ORATS `/hist/options` entitlement (external) — see `docs/ai/releases/R40.1/ORATS_BACKTEST_ENTITLEMENT.md`
- Universe V2 snapshot refresh on market hours
- Today ticket queue still device-local
- Independent Codex + Cowork acceptance still required for COMPLETE
