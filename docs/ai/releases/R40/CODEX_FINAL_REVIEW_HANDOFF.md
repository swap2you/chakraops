# Codex Final Adversarial Review — R40

Adapt from library `80_CODEX_FINAL_REVIEW.md`.

After Cursor believes R40 is complete, independently review `main`.

## Attempt to falsify readiness across
- governance / mainline controls (`SINGLE_OPERATOR_MAINLINE_LOOP_MODE`)
- architecture / source of truth (`strategy_profiles.yaml` runtime vs `threshold_registry.yaml` provenance)
- data / versioning / concurrency
- trading safety (manual only, no broker write, scheduler off)
- Universe lifecycle / membership
- Wheel / Share logic
- financial calculations / units (premium ×100, drawdown currency)
- Robinhood read-only enforcement (if present)
- **backtesting bias / overfit** (look-ahead in walk-forward; train/OOS leakage; optimizing for trade count)
- UX / Slack truthfulness (SIMULATION banners; journal lane vs Strategy Lab lane)
- operations (ports 18800/18873; operator daily runbook)
- tests / evidence (`tests/test_r400_*.py`)

## Return
BLOCKER / HIGH / MEDIUM / LOW / FALSE POSITIVE with exact evidence, reproduction, remediation, and GO/NO-GO.

## R40-specific checks
1. R27.5 journal backtest endpoints and `BacktestPage` replay still work.
2. R40 API always returns `simulation: true`, `manual_only: true`.
3. No production profile values changed without evidence_path.
4. Unit tests do not require live ORATS hist.
5. Overlapping train/OOS windows are rejected.

End:
`CHAKRAOPS R40 CODEX FINAL ADVERSARIAL REVIEW COMPLETE`
