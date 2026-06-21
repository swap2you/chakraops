# STATUS — R34.0

## Release
R34.0

## Branch
`release/R31-R35-program` (program milestone; single branch for R31–R35, milestone commits, one final PR)

## Objective
Consolidate the operator experience around trusted decisions, positions, backtests, and reports.

## Risk level
Level 3 — application refactor and analytical presentation

## Current status
CUTOVER COMPLETE (Phases 0–3), BROADER PRODUCT PHASES STAGED. The canonical decision engine is now the **authoritative producer of the primary live recommendation** at the API/data-contract layer (`/api/ui/action-needed` → `authoritative_recommendations`; Today + Symbol Diagnostics carry `decision_source`/`canonical_decision`); legacy lists are relabeled `diagnostic_non_authoritative`. R32 `stale_data_gate` enforced on the live actionable path. Recommendation-set capital safety added. Persistence decision documented (RETAIN; no migration). Gate-verified. Packet Phases 4–9 (dashboard/nav redesign, portfolio/universe UI, backtest engine, journal/reports, frontend overhaul) are **staged and NOT claimed complete**.

## Dependencies
R33.0 canonical decision and profile contracts (implemented + tested; Claude BLOCKED on live cutover, which R34 closes at the API/data layer).

## Cursor implementation
DELIVERED (cutover core): Phase 0 R33 claim correction (commit c82b353); Phase 1 canonical live cutover via `legacy_adapter.py` + `live_service.py` wired into `ui_routes.py` (action-needed/symbol-diagnostics/today) with `stale_data_gate` + `profile_overrides`→422; Phase 2 recommendation-set capital safety; Phase 3 persistence decision (`persistence_decision.md`, RETAIN). Frontend types/hook expose the authoritative block. STAGED (not done): packet Phases 4–9.

## Claude review
Re-review requested — canonical live cutover closes the R33 BLOCKER at the API/data layer (authoritative source = canonical engine; legacy non-authoritative; stale-data blocking on the live actionable path).

## Codex review
PENDING — Codex quota exhausted; review not run. No Codex approval claimed.

## Cowork UAT
Required — see UAT checklist in `notes.md`.

## Gates
- Backend: PASS — 1140 passed, 3 skipped (was 1127; +13 R34 tests)
- Frontend tests: PASS — 315 passed, 18 skipped (was 313; +2 R34 tests)
- Frontend build: PASS — vite ~6.7s (pre-existing chunk-size M-13 + dynamic-import notice; no errors)
- Release-specific validation: PASS — canonical-cutover proof, stale-data live-route proof, no-conflicting-primary, profile carried, manual-only, top 5–7 cap, capital-set warning, 422. Evidence: docs/ai/releases/R34.0/notes.md (+ local logs out/verification/R34.0/)

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- H-5 (dual decision/ranking): RESOLVED at the API/data-contract layer — canonical engine is the authoritative primary; legacy relabeled non-authoritative and evidenced. UI visual re-render onto the canonical block and legacy physical retirement are STAGED (packet Phase 4 / later cleanup).

## H-5 status
RESOLVED (live cutover evidenced at API/data layer). Visual dashboard re-render + legacy module retirement deferred to staged work.

## Next action
Claude re-review of the cutover + Cowork browser UAT + deferred Codex review before R35.0. Staged: packet Phases 4–9 (product consolidation) within R34's broader scope.

## Stop point
R34.0 cutover (Phases 0–3) complete, gate-verified, and pushed. Broader product phases staged. No PR, no tag, no deploy.
