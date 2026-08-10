# Current State — ChakraOps

_Last updated: 2026-08-10 — master program R36.3–R40 COMPLETE_

## Release Status

| Field | Value |
|-------|-------|
| Program | R36.3–R40 **COMPLETE — VALIDATED FOR MANUAL OPERATOR USE** |
| Current branch | `main` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Requirements | `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md` |
| Daily runbook | `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md` |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. Robinhood sync = **NO_GO** (manual portfolio). ORATS sole options provider. Scheduler disabled. Stay in cash is valid.

## Deferred (non-blocking)

- Universe V2 snapshot refresh on market hours
- Full ORATS historical options client
- Today ticket queue still device-local
