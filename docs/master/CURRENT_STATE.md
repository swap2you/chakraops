# Current State — ChakraOps

_Last updated: 2026-08-10 — **R41_R50_ACTIVE**_

## Release Status

| Field | Value |
|-------|-------|
| Program | `CHAKRAOPS R41–R50 OPERATOR PRODUCTIONIZATION PROGRAM` |
| Status | `R41_R50_ACTIVE` |
| Current branch | `main` |
| Mode | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Requirements | `docs/ai/MASTER_PROGRAM_R41_R50_REQUIREMENTS.md` |
| Baseline SHA | `e0813a889c0a93179f10e119bf03286e2b1cdb2e` |
| Daily runbook | `chakraops/docs/RUNBOOK_OPERATOR_DAILY.md` |

## Ports

| Service | Port |
|---------|------|
| Backend | http://127.0.0.1:18800 |
| Frontend | http://127.0.0.1:18873 |

## Trading Safety

Manual execution only. No auto-trading. No broker order routing. Robinhood sync = **NO_GO**. ORATS sole options provider. Scheduler disabled (fail-closed). Stay in cash is valid.

## Deferred / gaps

- ORATS `/hist/options` entitlement (external)
- Independent Codex + Cowork acceptance deferred to end of R50
- R42: Today/ticket device-local persistence migration
