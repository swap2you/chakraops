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
IMPLEMENTATION COMPLETE — **final lock-race and test-validity remediation active** (starting commit `662b81e`). Prior operational-integrity pass delivered strict journal/history integrity, ORATS downstream sanitization, and generated-file hygiene. **H-5 CLOSED.**

**Final external validation:** Claude final R34 review **APPROVED WITH NON-BLOCKING NOTES**; Cowork real-browser UAT **PASS WITH NOTES**; Codex final targeted review **BLOCKED** on (1) unsafe PID/liveness stale-lock reclamation race, (2) unreadable-journal test patching wrong API (`Path.read_text` vs production `open`), (3) tautological ORATS stage2_trace test calling `redact_secrets()` directly. This pass addresses those Codex blockers. R34 remains implementation complete — **not** externally approved — awaiting Codex targeted re-review before R35.0.

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
Final lock-race and test-validity remediation in progress (post-662b81e): OS-native cross-process lock (`fcntl`/`msvcrt`), production-path journal unreadability test, active ORATS pipeline stage2_trace path tests. Prior integrity pass: backend 1218/3 skipped; frontend 334/18 skipped; build PASS.

## Claude review
- Final R34 review: **APPROVED WITH NON-BLOCKING NOTES** (awaiting lock-race remediation re-review).

## Codex review
- Final targeted R34 review: **BLOCKED** — unsafe stale-lock reclamation race; invalid unreadable-journal test; tautological ORATS stage2_trace test. Remediation active. No Codex approval claimed.

## Cowork UAT
- Final real-browser UAT: **PASS WITH NOTES**. See `out/verification/R34.0/frontend_uat_plan.md`.

## Gates (lock-race remediation pass)
- Pending — OS-native lock multiprocessing tests, journal/ORATS path tests, full AGENTS.md gates.

## PR
Pending

## Merge
Pending

## Tag
Pending

## Open blockers
- Codex BLOCKED findings (lock race, journal test validity, ORATS active-path tests) — remediation in progress.

## H-5 status
**CLOSED (R34.0)** — API/data-contract layer fail-closed and authoritative; rendered-UI cutover complete on Dashboard/Today/Symbol; page-level cutover tests pass.

## Next action
Complete lock-race remediation, run gates, push implementation commit, await Codex targeted re-review before R35.0. No PR, no tag, no deploy.

## Stop point
R34.0 implementation complete; final Codex lock-race blockers under remediation. R35 not started.
