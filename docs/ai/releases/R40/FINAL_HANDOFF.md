# R40 Final Handoff

## Status
**TECHNICALLY_READY_WITH_EXTERNAL_BACKTEST_ENTITLEMENT_GAP** on `main`.

R40.1 holds final acceptance (`FINAL_ACCEPTANCE_HOLD`) until Codex + Cowork complete.
Fixture / Strategy Lab lane remains **SIMULATION**. `/hist/options` not entitled (see `../R40.1/ORATS_BACKTEST_ENTITLEMENT.md`).

## What shipped
- Parallel Strategy Lab research lane (`app/core/backtest/r40/*`)
- Metrics suite, fill model, walk-forward with look-ahead guard
- Threshold provenance registry (all inherited; runtime still `strategy_profiles.yaml`)
- Offline CLI `scripts/run_r40_simulation.py`
- Optional API `POST /api/ui/backtest/r40/run` + `GET /api/ui/backtest/r40/last`
- Light BacktestPage Strategy Lab section (journal replay preserved)
- Operator daily runbook
- Codex + Cowork handoff packets

## Safety unchanged
Manual only · no broker writes · scheduler off · no evidence-free threshold retune · SIMULATION labels on research outputs.

## Validation commands
```
cd chakraops && .\.venv\Scripts\python.exe -m pytest tests/test_r400_*.py tests/test_r401_*.py -q --tb=short
cd frontend && npm run build
```

## Next
1. Codex: `docs/ai/releases/R40.1/CODEX_FINAL_REVIEW_HANDOFF.md`
2. Cowork: `docs/ai/releases/R40.1/COWORK_FINAL_UAT_HANDOFF.md`
3. Remediate BLOCKER/HIGH only; then consider program completion string from master requirements.

## Known gaps
- ORATS `/hist/options` entitlement — external gap (403)
- Dividends / corporate actions / early assignment realism — limited
- No calibrated production thresholds yet (registry marks inherited)
