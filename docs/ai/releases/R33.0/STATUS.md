# STATUS — R33.0

## Release
R33.0

## Branch
`release/R31-R35-program` (program milestone; single branch for R31–R35, milestone commits, one final PR)

## Objective
Make ChakraOps recommendations mathematically consistent, profile-driven, portfolio-aware, and safely ranked.

## Risk level
Level 4 — trading-decision logic and financial risk

## Current status
TECHNICALLY IMPLEMENTED — AWAITING LIVE INTEGRATION. The canonical decision engine (engine, profiles, contract, gates, strategies, sizing, ranking) is implemented and tested, and the R32 stale-data gate protects canonical-engine actions. **Live application cutover is NOT yet complete:** Dashboard, Today, Symbol Diagnostics, `/api/ui/action-needed`, and related live surfaces still use the legacy evaluator/ranking stack, which retains its existing guards until the R34 cutover. **H-5 remains OPEN and is owned by R34.**

## Dependencies
R32.0 trusted data contracts and freshness gates (COMPLETE; Claude APPROVED-WITH-NOTES, notes closed in 049cb2f; Codex review PENDING — quota).

## Cursor implementation
IMPLEMENTED + TESTED (not yet live-authoritative) — `app/core/decision_engine/*` (canonical profiles + decision contract + gates + strategies + sizing + ranking + engine), `config/strategy_profiles.yaml`, advisory API `app/api/decision_engine_routes.py` (`/api/ui/decision-engine/*`), and frontend query contract. The R32 `stale_data_gate` is wired into the canonical engine's actionable paths. The engine is NOT yet the live source of truth for the primary recommendation surfaces; that live cutover is R34 (H-5).

## Claude review
BLOCKED — the canonical decision engine is internally correct and well-tested, but it is not yet the authoritative live recommendation path. Dashboard, Today, Symbol Diagnostics, `/api/ui/action-needed`, and related live surfaces still use the legacy evaluator/ranking stack. Live cutover (H-5) is assigned to R34.

## Codex review
PENDING — Codex quota exhausted; review not run. No Codex approval claimed.

## Cowork UAT
Required

## Gates
- Backend: PASS — 1127 passed, 3 skipped
- Frontend tests: PASS — 313 passed, 18 skipped
- Frontend build: PASS — vite ~7.1s (pre-existing chunk-size warning, M-13)
- Release-specific validation: PASS — golden vectors (6), profile matrix (4), risk invariants (6), stale/missing-data + gates (14). Evidence: out/verification/R33.0/

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- Claude R33 verdict: **BLOCKED** — canonical engine is not yet the authoritative live recommendation path. Resolution owned by R34 (live cutover, H-5).

## Next action
R34.0 closes the Claude blocker via canonical live cutover (H-5). Codex review remains PENDING (quota); no Codex approval claimed.

## Stop point
R33.0 technically implemented and pushed; Claude BLOCKED on live integration. H-5 reassigned to R34.
