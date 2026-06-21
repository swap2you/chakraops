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
COMPLETE — canonical decision engine, strategy profiles, portfolio-aware sizing/invariants, and deterministic ranking delivered and gate-verified on `release/R31-R35-program`. Advisory, manual-only.

## Dependencies
R32.0 trusted data contracts and freshness gates (COMPLETE; Claude APPROVED-WITH-NOTES, notes closed in 049cb2f; Codex review PENDING — quota).

## Cursor implementation
COMPLETE — `app/core/decision_engine/*` (canonical profiles + decision contract + gates + strategies + sizing + ranking + engine), `config/strategy_profiles.yaml`, read-only API `app/api/decision_engine_routes.py`, and frontend query contract. R32 `stale_data_gate` wired into every actionable path. Packet normalized with exact paths before source edits.

## Claude review
Pending (R33 completed milestone)

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
None recorded

## Next action
Claude review + deferred Codex review before R34.0. Do not start R34.

## Stop point
R33.0 complete and pushed. Awaiting Claude review and deferred Codex review.
