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
COMPLETE (pending final external validation). The final pass (authorization commit `30ffa7f` `docs(R34.0): authorize final cutover remediation paths`, implementation commit `R34.0: complete rendered canonical cutover and product hardening`) delivers all required Phase 7 items: transaction-safe weekly refresh (cross-process lock + journal recovery), complete ORATS application-path redaction (no bare token-bearing rethrows; snippets sanitized at construction; secret scan 0 hits), live sector enforcement, **rendered** canonical cutover (Dashboard/Today/Symbol render the authoritative block as primary; legacy demoted to a collapsed diagnostics section), shared-table DOM fix, Backtest SIMULATION label, positions pagination, and navigation grouping. **H-5 is CLOSED** — rendered-UI cutover page tests pass. Awaiting final Claude, Codex, and Cowork R34 validation before R35.0.

### Prior (safety) remediation pass — already delivered + gate-verified:
- Phase 1 — weekly universe refresh is now **operational** (computes → applies via the canonical overlay store → appends exactly one history record; idempotent per ISO week; atomic with rollback; admin POST `/api/ui/universe/weekly-refresh/apply`; R35 still owns scheduling).
- Phase 2 — **ORATS credential log redaction** (central `app/core/security/redact.py`; wired into all ORATS request-failure/log/exception sites and the data-health/boot-probe/503 paths).
- Phase 3 — **fail-closed canonical live computation** (`/api/ui/action-needed`, `_attach_canonical_decision`): canonical authority is never claimed when canonical output is absent; no legacy actionable fallback; explicit degraded contract with empty actionable + reason code.
- Phase 4 — **missing-cash and sector safety**: available cash is never inferred from total equity; cash-consuming CSP/share-buy are non-actionable when cash is unknown; covered calls may proceed; sector concentration that cannot be evaluated is surfaced, not silently ignored.
- `/api/view/daily-overview` normalized with canonical decision-source markers.

### Final cutover pass — delivered + gate-verified:
- Phase 1 — **transaction-safe** weekly refresh: one cross-process lock spanning idempotency → snapshot → overlay → history → completion; atomic temp-file writes (flush+fsync+`os.replace`); journal-based deterministic recovery; rollback/recovery failure raises `WeeklyRefreshCriticalError` (never ignored); admin route returns controlled APPLIED/SKIPPED_IDEMPOTENT/FAILED/CRITICAL status. No scheduler.
- Phase 2 — **complete** ORATS application-path redaction: sanitized at exception construction; `RequestException` wrapped (`from None`, no bare token-bearing rethrow); response bodies/snippets/headers/diagnostics/boot-probe/HTTP errors all redacted; fake-secret regression tests; secret scan 0 hits in tracked code + evidence.
- Phase 3 — **live sector enforcement**: symbol→sector mapping + existing sector exposure from portfolio data; profile sector caps enforced; incremental CSP/share-buy BLOCKED when sector data unavailable; existing-share covered calls flagged `SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION`; deterministic reason codes.
- Phase 4 — **rendered** canonical cutover: `AuthoritativeRecommendations` is the Dashboard/Today primary; legacy `top_options`/`top_shares` collapsed under `Diagnostics — non-authoritative legacy output`; page-level tests prove canonical primary, demotion, stale/unavailable fail-closed, 5–7 cap, manual-only wording, profile + capital safety.
- Phase 5 — **Symbol Diagnostics**: backend `_canonical_decision_for_symbol` populates the canonical decision; UI renders it primary, legacy explanatory; NOT-EVALUATED + Recompute for absent symbols; no raw FAIL_/WARN_/PASS.
- Phase 6 — **frontend correctness**: shared-table `<tr>`-in-`<tr>` DOM fix; Backtest SIMULATION label; positions pagination; logical navigation grouping; understandable loading/empty/stale/unavailable/failure states.

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

## Gates (final cutover pass)
- Backend: PASS — 1200 passed, 1 skipped
- Frontend tests: PASS — 334 passed, 18 skipped
- Frontend build: PASS (only pre-existing chunk-size + dynamic/static-import warnings — deferred to post-R35 per Phase 7 scope boundary)
- Secret scan: PASS — 0 real-token hits in tracked code and in evidence
- Evidence: out/verification/R34.0/ (notes.md, changed_files.md, weekly_refresh_transaction.md, secret_redaction.md, sector_enforcement.md, rendered_canonical_cutover.md, frontend_uat_plan.md, backend.log, frontend.log, build.log)

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- None for R34 scope. All Phase 7 required items delivered and gate-verified. Post-R35 enhancements (drag-and-drop dashboard, broad visual redesign, physical legacy-module deletion, bundle/code-split architecture, multi-user DB architecture) remain explicitly out of R34 scope.

## H-5 status
**CLOSED (R34.0)** — API/data-contract layer fail-closed and authoritative; rendered-UI cutover complete on Dashboard/Today/Symbol; page-level cutover tests pass (`DashboardPage.canonical.test.tsx`, `TodayPage.canonical.test.tsx`, `SymbolDiagnosticsPage.canonical.test.tsx`). Physical legacy-module retirement deferred to post-R35.

## Next action
Final Claude re-review, Codex re-review, and real-browser Cowork UAT of R34.0; then proceed to R35.0. No PR, no tag, no deploy until validated.

## Stop point
R34.0 complete: transaction-safe weekly refresh, complete ORATS redaction, live sector enforcement, rendered canonical cutover, Symbol Diagnostics canonical/empty-state, table DOM fix, SIMULATION label, navigation grouping, positions pagination — all gate-verified and pushed. H-5 closed. No PR, no tag, no deploy. R35 not started.
