# R40 Final Handoff

## Status
**IMPLEMENTED** on `main` (baseline start `386d7aa` + R40 changes). Awaiting Codex adversarial review + Cowork UAT before program-complete string.

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
cd chakraops && .\.venv\Scripts\python.exe -m pytest tests/test_r400_*.py -q --tb=short
cd frontend && npm run build
```

## Next
1. Codex: `docs/ai/releases/R40/CODEX_FINAL_REVIEW_HANDOFF.md`
2. Cowork: `docs/ai/releases/R40/COWORK_FINAL_UAT_HANDOFF.md`
3. Remediate BLOCKER/HIGH only; then consider program completion string from master requirements.

## Known gaps
- ORATS historical options client for full multi-year chains — future
- Dividends / corporate actions / early assignment realism — limited
- No calibrated production thresholds yet (registry marks inherited)
