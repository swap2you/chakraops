# ChakraOps Program Status

Last updated: 2026-08-10 (master program R36.3–R40 **COMPLETE** — validated for manual operator use)

## Workflow

- **Mode:** `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` (see `AGENTS.md`)
- **Branch:** `main`
- **Baseline SHA at program start:** `63d83d00e3ceb9ac15a080a54178adf0d7e78267`
- **Canonical requirements:** `docs/ai/MASTER_PROGRAM_R36_3_R40_REQUIREMENTS.md`
- Cursor is the only writing agent unless the operator grants a narrow exception.

| Release | Status | Notes |
|---|---|---|
| R31.0–R35.0 | MERGED | historical |
| R35.1 | MERGED | dedicated ports |
| R35.2 | MERGED | ops hardening |
| R36.1 | MERGED | explainability |
| R36.2 | MERGED | Universe V2 |
| R36.3 | VALIDATED | whole-app trust |
| R37 | NO_GO | Robinhood RO unavailable; manual portfolio |
| R38 | VALIDATED | Wheel & Share V2 |
| R39 | VALIDATED | Command Center / Opportunities / Slack |
| R40 | VALIDATED | backtest lane + calibration registry + runbook |

## Final

See `docs/ai/releases/R40/FINAL_HANDOFF.md` and `docs/ai/validation/R40_ACCEPTANCE_MANIFEST.json`.

Optional independent Codex/Cowork handoffs remain under `docs/ai/releases/R40/` for operator re-confirmation.
