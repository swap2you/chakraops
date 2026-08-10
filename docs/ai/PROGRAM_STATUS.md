# ChakraOps Program Status

Last updated: 2026-08-10 (R40.1 Final Acceptance Stabilization — **FINAL_ACCEPTANCE_HOLD**)

## Workflow

- **Mode:** `SINGLE_OPERATOR_MAINLINE_LOOP_MODE` (see `AGENTS.md`)
- **Branch:** `main`
- **Baseline SHA (R40.1 start):** `99eb213`
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
| R40 | TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP | fixture SIMULATION; `/hist/options` not entitled |
| R40.1 | FINAL_ACCEPTANCE_HOLD | scheduler/eval/cash/ORATS/universe stabilization |

## Final

See `docs/ai/releases/R40.1/R40_1_ACCEPTANCE.md` and `docs/ai/releases/R40.1/ORATS_BACKTEST_ENTITLEMENT.md`.

Independent Codex/Cowork handoffs: `docs/ai/releases/R40.1/CODEX_FINAL_REVIEW_HANDOFF.md`, `COWORK_FINAL_UAT_HANDOFF.md`.

Do **not** claim program COMPLETE until independent acceptance completes.
