# ChakraOps Program Status

Last updated: 2026-08-10 (master program R36.3–R40 started; SINGLE_OPERATOR_MAINLINE_LOOP_MODE authorized)

## Workflow

- **Mode:** `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` (see `AGENTS.md`)
- **Branch:** `main` (direct commits; push only after release acceptance green)
- **Baseline SHA at program start:** `63d83d00e3ceb9ac15a080a54178adf0d7e78267`
- **Canonical requirements:** `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md`
- Cursor is the only writing agent unless the operator grants a narrow exception.

| Release | Status | Next action |
|---|---|---|
| R31.0–R35.0 | MERGED (historical program) | — |
| R35.1 | MERGED | — |
| R35.2 | MERGED | — |
| R36.1 | MERGED | — |
| R36.2 | MERGED | — |
| R36.3 | ACTIVE | Whole-app trust & wiring stabilization |
| R37 | READY_TO_START | After R36.3 |
| R38 | READY_TO_START | After R37 (or R37 NO-GO) |
| R39 | READY_TO_START | After R38 |
| R40 | READY_TO_START | After R39; closes master program |

## Status values

`READY_TO_START`, `ACTIVE`, `BLOCKED`, `IMPLEMENTED`, `VALIDATED`, `MERGED`, `NO_GO`, `DEFERRED`.
