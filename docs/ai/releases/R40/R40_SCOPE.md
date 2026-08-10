# R40 — Backtesting, Calibration & Production Readiness — Scope

## Purpose
Add a **parallel Strategy Lab research lane** (walk-forward / OOS metrics, fill model, threshold provenance) without rewriting R27.5 journal backtest. Close the master program with operator daily runbook + review handoffs.

## Baseline
- `main` @ `386d7aa` (R39 Command Center / Slack / UX Consolidation)
- Safety: manual-only, scheduler off, no broker writes, no evidence-free threshold retune
- Runtime decisioning continues to read `config/strategy_profiles.yaml`

## In scope
| ID | Deliverable |
|---|---|
| R40-B1 | Fixture/synthetic portfolio simulation path (ORATS hist client deferred) |
| R40-B2 | Walk-forward train→freeze→OOS; simple fill/slippage model; look-ahead guards |
| R40-B3 | Metrics: expectancy, drawdown, premium yield, capital util, assignment, win/loss, PF, tail p95, recovery_bars |
| R40-T1 | `threshold_registry.yaml` provenance overlay (all keys `inherited`); loader `get_threshold_provenance` |
| R40-P1 | `RUNBOOK_OPERATOR_DAILY.md` + production readiness notes |
| R40-R1 | Codex final review + Cowork final UAT handoff packets |

## Out of scope / bans
- Rewriting R27.5 journal backtest
- Live ORATS historical options required for unit tests
- Production profile retune without evidence
- Broker write / order routing / scheduler enable
- Optimizing for trade count

## Validation
```
cd chakraops && .\.venv\Scripts\python.exe -m pytest tests/test_r400_*.py -q --tb=short
cd frontend && npm run build
```
