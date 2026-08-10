# ChakraOps Program Status

Last updated: 2026-08-10 — **CHAKRAOPS R41–R50 OPERATOR PRODUCTIONIZATION PROGRAM**

## Active program

| Field | Value |
|-------|-------|
| Program | `CHAKRAOPS R41–R50 OPERATOR PRODUCTIONIZATION PROGRAM` |
| Status | `R41_R50_ACTIVE` |
| Workflow | `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` |
| Branch | `main` |
| Baseline SHA | `e0813a889c0a93179f10e119bf03286e2b1cdb2e` |
| Requirements | Dropbox library `ChakraOps_R41_R50_Operator_Productionization` + `docs/ai/MASTER_PROGRAM_R41_R50_REQUIREMENTS.md` |

Do **not** claim `R41_R50_TECHNICALLY_COMPLETE_PENDING_INDEPENDENT_ACCEPTANCE` or operator-ready COMPLETE while status is `R41_R50_ACTIVE`.

## Safety (permanent)

manual_only · trade_execution=false · no broker writes · Robinhood NO_GO · ORATS-only · scheduler/legacy/nightly/EOD disabled by default · Stay in Cash valid · no evidence-free threshold retune · do not fake `/hist/options` entitlement.

## Prior releases

| Release | Status | Notes |
|---|---|---|
| R31–R39 | MERGED / VALIDATED | historical |
| R40 | TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP | fixture SIMULATION |
| R40.1 | ROLLED INTO R50 INDEPENDENT ACCEPTANCE | scheduler/eval/cash/ORATS/universe; independent Codex/Cowork deferred to R50 |
| R41–R50 | IN PROGRESS | operator productionization |

## Current release focus

See `docs/ai/releases/R41/` onward. Writer: Cursor only.
