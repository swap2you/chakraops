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
INCOMPLETE / FINAL REMEDIATION ACTIVE. Post-safety-remediation review: **Claude** APPROVED WITH NON-BLOCKING NOTES for the safety remediation but R34 INCOMPLETE; **Codex** BLOCKED; **Cowork** real-browser UAT PASS WITH NOTES with rendered canonical cutover incomplete. The final pass (authorization commit `docs(R34.0): authorize final cutover remediation paths`) delivers: transaction-safe weekly refresh (cross-process lock + journal recovery), complete ORATS application-path redaction (no bare token-bearing rethrows; snippets sanitized at construction), live sector enforcement, **rendered** canonical cutover (Dashboard/Today/Symbol render the authoritative block as primary; legacy demoted to a collapsed diagnostics section), table DOM fix, Backtest SIMULATION label, positions pagination, and nav grouping. H-5 closes only after rendered-UI cutover tests pass.

### Prior (safety) remediation pass — already delivered + gate-verified:
- Phase 1 — weekly universe refresh is now **operational** (computes → applies via the canonical overlay store → appends exactly one history record; idempotent per ISO week; atomic with rollback; admin POST `/api/ui/universe/weekly-refresh/apply`; R35 still owns scheduling).
- Phase 2 — **ORATS credential log redaction** (central `app/core/security/redact.py`; wired into all ORATS request-failure/log/exception sites and the data-health/boot-probe/503 paths).
- Phase 3 — **fail-closed canonical live computation** (`/api/ui/action-needed`, `_attach_canonical_decision`): canonical authority is never claimed when canonical output is absent; no legacy actionable fallback; explicit degraded contract with empty actionable + reason code.
- Phase 4 — **missing-cash and sector safety**: available cash is never inferred from total equity; cash-consuming CSP/share-buy are non-actionable when cash is unknown; covered calls may proceed; sector concentration that cannot be evaluated is surfaced, not silently ignored.
- `/api/view/daily-overview` normalized with canonical decision-source markers.

STAGED / NOT COMPLETE (must not be claimed done): Phase 5 (rendered visual cutover in Dashboard/Today/Symbol) and Phase 6 (full product scope — nav consolidation, portfolio/positions, universe/data-health pages, backtest engine, journal/reports reconciliation, frontend-quality M-13/nested-table).

## Dependencies
R33.0 canonical decision and profile contracts (implemented + tested).

## Cursor implementation
DELIVERED this pass: Phases 1–4 + daily-overview source markers, with new tests (`test_r340_orats_log_redaction.py`, `test_r340_weekly_refresh_operational.py`, `test_r340_canonical_failclosed.py`, `test_r340_missing_cash_sector.py`) and updated `test_r340_live_cutover.py`. STAGED: Phase 5 (rendered UI), Phase 6 (product scope).

## Claude review
- Safety remediation: APPROVED WITH NON-BLOCKING NOTES — but R34 INCOMPLETE (rendered cutover, transaction-safe refresh, complete redaction, sector enforcement outstanding). Addressed in the final pass. Re-review required.

## Codex review
- Consolidated R32–R34: **BLOCKED**. Final pass addresses concurrency/atomicity of weekly refresh, complete ORATS redaction (bare rethrows + raw snippets), and rendered cutover. Re-review required. No Codex approval claimed.

## Cowork UAT
- Real-browser UAT: PASS WITH NOTES — rendered canonical cutover incomplete. Final pass renders the canonical block as primary on Dashboard/Today/Symbol and demotes legacy. Re-UAT required. See `out/verification/R34.0/frontend_uat_plan.md`.

## Gates (this remediation pass)
- Backend: PASS — 1169 passed, 1 skipped
- Frontend tests: PASS — 315 passed, 18 skipped
- Frontend build: PASS (known M-13 chunk-size + UniverseAdminPage nested-table warnings — staged Phase 6)
- Evidence: out/verification/R34.0/ (notes.md, canonical_cutover.md, changed_files.md, persistence_decision.md, browser_uat_plan.md, gate logs)

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- H-5 (dual decision/ranking): **OPEN**. Fail-closed canonical authority is enforced at the API/data-contract layer, but the rendered UI (Dashboard/Today/Symbol) still shows legacy primary lists. H-5 cannot be closed until Phase 5 ships and its page-level cutover tests pass.
- Phase 5 (rendered visual cutover) and Phase 6 (full product scope): not started.

## H-5 status
OPEN — API/data-contract layer fail-closed and authoritative; rendered-product cutover STAGED (Phase 5). Close only after rendered-UI cutover tests pass.

## Next action
Phase 5 rendered cutover + Phase 6 product scope; then Claude re-review, Codex re-review, and real-browser Cowork UAT before R35.0.

## Stop point
Consolidated R32–R34 safety/security/correctness blockers remediated, gate-verified, and pushed. R34.0 is NOT complete: Phase 5 (rendered cutover) and Phase 6 (product scope) remain. No PR, no tag, no deploy.
