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
IMPLEMENTATION COMPLETE — **final operational-integrity remediation active** (starting commit `50aa600`). Prior cutover pass delivered transaction-safe weekly refresh, complete ORATS application-path redaction, live sector enforcement, rendered canonical cutover, shared-table DOM fix, Backtest SIMULATION label, positions pagination, and navigation grouping. **H-5 CLOSED.**

**Final external validation:** Claude final R34 review **APPROVED WITH NON-BLOCKING NOTES**; Cowork real-browser UAT **PASS WITH NOTES**; Codex final R34 review **BLOCKED** on refresh integrity, remaining ORATS redaction, authorization reconciliation, and generated-file hygiene. This pass addresses Codex blockers. R34 is described as implementation complete — **not** externally approved — awaiting Codex targeted re-review before R35.0.

**Operator waiver (2026-06-22d):** The operator explicitly accepts the historical exact-path deviation in commit `50aa600`. Documented waiver only — not retroactive authorization and not permission to repeat the pattern.

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
Final operational-integrity remediation delivered (post-0e860f5): strict journal/history integrity, ownership-safe cross-process lock, downstream ORATS sanitization, generated-file hygiene. Gates: backend 1218/3 skipped; frontend 334/18 skipped; build PASS; secret scan 0 hits.

## Claude review
- Final R34 review: **APPROVED WITH NON-BLOCKING NOTES** (implementation complete; integrity remediation addresses remaining notes).

## Codex review
- Final R34 review: **BLOCKED** — findings remediated in integrity pass (journal/history, ownership-safe lock, downstream ORATS, generated-file hygiene). Awaiting Codex targeted re-review. No Codex approval claimed.

## Cowork UAT
- Final real-browser UAT: **PASS WITH NOTES**. See `out/verification/R34.0/frontend_uat_plan.md`.

## Gates (integrity remediation pass)
- Backend: PASS — 1218 passed, 3 skipped
- Frontend tests: PASS — 334 passed, 18 skipped
- Frontend build: PASS
- Secret scan: PASS — 0 real-token hits in tracked code
- Evidence: out/verification/R34.0/ (final_integrity_notes.md, refresh_corruption_recovery.md, lock_ownership.md, downstream_orats_redaction.md, generated_file_hygiene.md, backend.log, frontend.log, build.log)

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
Awaiting Codex targeted re-review of integrity remediation before R35.0. No PR, no tag, no deploy.

## Stop point
R34.0 implementation complete; integrity remediation delivered and gate-verified. H-5 closed. Awaiting Codex re-review. R35 not started.
