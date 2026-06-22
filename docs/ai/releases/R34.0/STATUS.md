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
IMPLEMENTATION COMPLETE — **final lock-race and test-validity remediation delivered** (authorization `9f6130e`, starting commit `662b81e`). OS-native cross-process lock replaces unsafe stale-lock reclamation; journal unreadability test exercises production `open`; ORATS stage2_trace test drives real `fetch_option_chain` path. **H-5 CLOSED.**

**Final external validation:** Claude final R34 review **APPROVED WITH NON-BLOCKING NOTES**; Cowork real-browser UAT **PASS WITH NOTES**; Codex final targeted review was **BLOCKED** on lock race, journal test validity, and tautological ORATS tests — **remediated and gate-verified**. Awaiting Codex targeted re-review before R35.0. No Codex approval claimed.

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
Final lock-race and test-validity remediation delivered (post-9f6130e): OS-native cross-process lock (`fcntl`/`msvcrt`), production-path journal unreadability test, active ORATS pipeline stage2_trace path test. Gates: backend 1219/3 skipped; frontend 334/18 skipped; build PASS; R32/R33/R34 targeted 202 passed; secret scan 0 hits.

## Claude review
- Final R34 review: **APPROVED WITH NON-BLOCKING NOTES**. Awaiting re-review after lock-race remediation.

## Codex review
- Final targeted R34 review was **BLOCKED** (lock reclaim race; journal test validity; ORATS active-path tests). Remediation delivered and gate-verified. Awaiting Codex targeted re-review. No Codex approval claimed.

## Cowork UAT
- Final real-browser UAT: **PASS WITH NOTES**. See `out/verification/R34.0/frontend_uat_plan.md`.

## Gates (lock-race remediation pass)
- Backend: PASS — 1219 passed, 3 skipped
- Frontend tests: PASS — 334 passed, 18 skipped
- Frontend build: PASS
- R32/R33/R34 targeted: PASS — 202 passed
- Windows multiprocessing lock tests: PASS — 7 passed (spawn, not skipped)
- Secret scan: PASS — 0 real-token hits in tracked code
- Evidence: `out/verification/R34.0/` (`final_lock_race_remediation.md`, `windows_multiprocess_lock.md`, `journal_test_validity.md`, `orats_active_path_redaction.md`, `backend.log`, `frontend.log`, `build.log`)

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- External Codex re-review pending (implementation blockers closed).

## H-5 status
**CLOSED (R34.0)**

## Next action
Await Codex targeted re-review before R35.0. No PR, no tag, no deploy.

## Stop point
R34.0 final Codex blockers remediated and pushed. Awaiting targeted Codex and Claude approval before R35.0.
