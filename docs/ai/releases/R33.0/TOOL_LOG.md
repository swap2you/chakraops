# TOOL LOG — R33.0

## ChatGPT
- Program scope prepared.
- Status: packet ready.

## Cursor
- 2026-06-21: Started R33.0 on `release/R31-R35-program` (base 049cb2f). Normalized the R33 packet with exact authorized paths (replaced generic domains) before source edits; STATUS set ACTIVE.
- Plan: implement one canonical decision-engine package (`app/core/decision_engine/*`) for strategy profiles and the decision input/output contract, with regime/earnings/liquidity/holdings/cash gates, the R32 `stale_data_gate` wired into the canonical engine's actionable paths, portfolio-aware sizing with hard risk invariants, and deterministic top-5–7 ranking with blocked/watch/cash separation. Advisory, manual-only; no order routing.
- 2026-06-21: Implemented profiles.py + config/strategy_profiles.yaml, contract.py, gates.py, strategies.py, sizing.py, ranking.py, engine.py, and read-only API decision_engine_routes.py (mounted under /api/ui). Added frontend types + `useDecisionProfiles`/`useEvaluateDecisions`.
- Tests: 11 backend suites (profiles, contract, golden vectors, gates, strategies, sizing invariants, ranking, profile matrix, stale/missing-data, API, backward-compat) + 1 frontend suite; R34 backtest fixtures (no performance claims).
- Gates: Backend 1127 passed/3 skipped; Frontend 313 passed/18 skipped; Build passed. R33 financial/invariant suites green. Evidence in out/verification/R33.0/.
- Scope: H-5 dual decision/ranking stacks were NOT closed in R33. The canonical engine is implemented and tested but is NOT yet the authoritative live recommendation path; the legacy evaluator/ranking stack still drives Dashboard/Today/Symbol-Diagnostics/`/api/ui/action-needed` and keeps its existing guards. **H-5 remains OPEN and is owned by R34** (live cutover).
- Milestone committed and pushed as `R33.0: decision engine, strategy profiles, and risk correctness`. Did not start R34; no PR; no deploy.
- 2026-06-21 (post-review): Claude reviewed completed R33.0 and returned **BLOCKED** — engine internally correct/tested but not the authoritative live path. Recorded here and in STATUS.md. Earlier R33 wording ("every actionable path", "H-5 superseded", "live source of truth") corrected in `fix(R33.0): correct live-cutover claims and assign H-5 to R34`. Codex review remains PENDING (quota); no Codex approval claimed.

## Claude Code
- Pending.

## Codex
- Pending.

## Claude Cowork
- Pending UAT.

## Operator
- Pending approval.
