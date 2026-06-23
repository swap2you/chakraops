# R34.0 Release Packet — Unified Product Experience, Backtest, Database, and Reporting

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 3 — application refactor and analytical presentation

## Objective

Consolidate the operator experience around trusted decisions, positions, backtests, and reports.

## Dependencies

R33.0 canonical decision and profile contracts.

## Scope


Implement the approved navigation and page consolidation, remove duplicated information, fix table/DOM issues, present profile-aware decisions, harden backtest semantics, and establish lightweight retention/reporting. Preserve clear separation between live/manual decisions, simulations, and historical reports.


## Required deliverables


- consolidated navigation and page ownership
- dashboard/today/action-center flow
- portfolio and position lifecycle views
- universe/data-health views
- strategy profile controls
- backtest inputs, assumptions, and result labeling
- journal and monthly/weekly reports
- one deliberate persistence decision before any schema change (see "Persistence decision" section)
- database migrations/retention policy
- CSV/export and backup/restore support
- performance and bundle improvements where justified
- heavy jobs/calculations run outside request handlers


## Persistence decision (mandatory, before any database change)

R34 must make exactly **one deliberate persistence decision** and document it
**before** changing any database schema or framework. No database migration may
occur in R32. Do not change frameworks without evidence. Avoid repeated
database migrations.

Before any schema change, R34 must evaluate and document in the R34 evidence
folder (`out/verification/R34.0/persistence_decision.md`):

- expected daily and annual data volume
- market snapshot retention
- decision and recommendation history
- position and journal history
- backtest reproducibility
- report performance
- job-run and provider-request audit history
- backup and restore
- migration rollback
- partitioning, retention, and archival
- local resource footprint

Decision rules:

- If the current database is **retained**, document why it meets these
  long-term requirements (volume, retention, reproducibility, performance,
  backup/restore, local footprint).
- If the current database is **insufficient**, R34 performs **one controlled
  migration** with backup, forward migrations, rollback, and compatibility
  tests — never a destructive migration without backup.
- Heavy jobs and calculations must run **outside request handlers**.
- Drag-and-drop dashboard customization is **optional** and must not delay core
  usability.

R34 must retain, regardless of the persistence decision: dashboard
consolidation, duplicate-content removal, navigation simplification, backtest
clarity, reporting, and data-retention work.

This guardrail builds on the R32.0 data-reliability layer
(`app/core/data_reliability/*`, weekly universe refresh + JSONL refresh
history, freshness/stale-data gate). R32 deliberately used append-only files —
not new schema — to avoid premature migration; R34 owns the persistence
decision.

## Claude R33 blocker (R34 must close first)

R33 implemented and tested the canonical decision engine but did **not** make it the authoritative live recommendation path. Dashboard, Today, Symbol Diagnostics, and `/api/ui/action-needed` still use the legacy `staged_evaluator → evaluation_service_v2 → DecisionArtifactV2` batch pipeline plus request-time `next_action_r241`. **R34 closes H-5 by making the canonical engine the authoritative PRIMARY producer for these live surfaces (adapter-based), before any general UI cleanup.**

## Allowed tracked paths

Exact paths (identified by repository inspection of the live recommendation path). Generic domain-only permissions removed.

### Phase 0 — governance (R33 claim correction)
- `docs/ai/releases/R33.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`
- `chakraops/docs/releases/R33.0_release_notes.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`
- `docs/ai/PROGRAM_STATUS.md`, `docs/master/CURRENT_STATE.md`, `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`

### Phase 1–2 — canonical live cutover + capital-set safety (closes H-5)
- NEW `chakraops/app/core/decision_engine/legacy_adapter.py` — canonical `DecisionOutput` → live UI shapes (`next_action_code`, action-needed item, etc.); no FAIL_/WARN_ leakage.
- NEW `chakraops/app/core/decision_engine/live_service.py` — builds `DecisionInput`s from the persisted v2 artifact + portfolio, runs the canonical engine, applies recommendation-set capital safety, returns the authoritative primary recommendations.
- MODIFIED `chakraops/app/api/ui_routes.py` — `/api/ui/action-needed` (and the symbol-diagnostics builder) surface the canonical authoritative block; legacy fields relabeled non-authoritative/diagnostic; `stale_data_gate` enforced on the live actionable path.
- MODIFIED `chakraops/app/api/decision_engine_routes.py` — invalid `profile_overrides` returns HTTP 422 (not 500).
- MODIFIED `frontend/src/api/{types.ts,queries.ts}` — types/hook for the authoritative live recommendation block + capital-set warning (read-only).

### Phase 3 — persistence decision (no schema change unless justified)
- `out/verification/R34.0/persistence_decision.md` (evidence; decision documented before any DB change)

### Tests
- `chakraops/tests/test_r340_live_cutover.py` — canonical authoritative source, stale-data blocking, no conflicting primary, profile carried, manual-only, top 5–7 cap, capital-set warning, action-needed route markers (consolidated)
- `chakraops/tests/test_r340_profile_overrides_422.py` — invalid profile/overrides → HTTP 422
- `frontend/src/api/queries.liveDecision.test.tsx` — authoritative live recommendation hook

### Docs / governance
- `docs/ai/releases/R34.0/{STATUS,TOOL_LOG}.md`
- `chakraops/docs/releases/R34.0_requirements.md`, `R34.0_release_notes.md`
- `docs/ai/PROGRAM_STATUS.md`, `docs/master/CURRENT_STATE.md`, `chakraops/docs/releases/RELEASE_CHECKLIST.md`

### Consolidated R32–R34 blocker remediation (2026-06-22) — exact authorized paths
Codex consolidated R32–R34 = BLOCKED; Claude R34 = APPROVED WITH NON-BLOCKING NOTES (narrow API cutover only); Cowork = PASS WITH NOTES (narrow API cutover only). This pass closes the concrete safety/security/correctness blockers. Generic domain permissions removed — exact tracked paths only:

Phase 1 — operational weekly universe refresh:
- MODIFIED `chakraops/app/core/universe/weekly_refresh.py` — `apply_weekly_universe_refresh()` orchestrator (compute → apply → append one history record; idempotent; atomic rollback).
- MODIFIED `chakraops/app/core/universe/universe_overrides.py` — `apply_effective_universe()` (atomic bulk overlay), `snapshot_overlay()`, `restore_overlay()`.
- MODIFIED `chakraops/app/api/ui_routes.py` — admin POST `/api/ui/universe/weekly-refresh/apply` (R35 still owns scheduling).
- NEW `chakraops/tests/test_r340_weekly_refresh_operational.py`.

Phase 2 — ORATS credential log redaction:
- NEW `chakraops/app/core/security/__init__.py`, `chakraops/app/core/security/redact.py`.
- MODIFIED ORATS request/log/exception sites: `app/core/orats/{orats_client,orats_opra,orats_core_client,orats_equity_quote}.py`, `app/core/options/providers/orats_client.py`, `app/core/options/orats_chain_pipeline.py`, `app/core/options/v2/{csp,cc}_chain_v2.py`, `app/core/eligibility/providers/orats_daily_provider.py`, `app/api/data_health.py`, `app/api/server.py`.
- NEW `chakraops/tests/test_r340_orats_log_redaction.py` (FAKE token only).

Phase 3 — fail-closed canonical computation:
- MODIFIED `chakraops/app/api/ui_routes.py` (`ui_action_needed`, `_attach_canonical_decision`), `chakraops/app/api/server.py` (`/api/view/daily-overview` source markers).
- NEW `chakraops/tests/test_r340_canonical_failclosed.py`.

Phase 4 — missing-cash/sector safety:
- MODIFIED `chakraops/app/core/decision_engine/live_service.py`.
- NEW `chakraops/tests/test_r340_missing_cash_sector.py`.

Governance/evidence (authorized for edit):
- `docs/ai/releases/R34.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`, `docs/ai/releases/R32.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`
- `docs/ai/PROGRAM_STATUS.md`, `docs/master/CURRENT_STATE.md`, `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`
- `chakraops/docs/releases/{R34.0_requirements,R34.0_release_notes,RELEASE_CHECKLIST}.md`
- `out/verification/R34.0/*` (local ignored evidence)

### Final R34 cutover remediation (2026-06-22b) — exact authorized paths
Review status: Claude APPROVED WITH NON-BLOCKING NOTES (safety remediation) but R34 INCOMPLETE; Codex BLOCKED; Cowork real-browser UAT PASS WITH NOTES (rendered canonical cutover incomplete). This pass completes the required R34 outcomes. Generic domains removed — exact tracked paths only:

Phase 1 — transaction-safe weekly universe refresh:
- MODIFIED `chakraops/app/core/universe/weekly_refresh.py` — cross-process-locked transaction (idempotency→snapshot→apply→history) with journal/marker recovery; controlled outcome status.
- MODIFIED `chakraops/app/core/universe/universe_overrides.py` — atomic temp-file write (flush+fsync+`os.replace`).
- MODIFIED `chakraops/app/core/universe/refresh_history_store.py` — atomic append (temp+fsync+`os.replace`).
- NEW `chakraops/app/core/universe/refresh_lock.py` — cross-process file lock + transaction journal helpers.
- MODIFIED `chakraops/app/api/ui_routes.py` — admin route returns controlled success/idempotent-skip/failure.
- NEW `chakraops/tests/test_r340_weekly_refresh_transaction.py`.

Phase 2 — complete ORATS redaction:
- MODIFIED `chakraops/app/core/security/redact.py` (helpers as needed).
- MODIFIED `chakraops/app/core/orats/{orats_client,orats_core_client,orats_equity_quote,orats_opra}.py`.
- MODIFIED `chakraops/app/core/options/providers/{orats_client,orats_provider}.py`, `chakraops/app/core/options/{orats_chain_pipeline,orats_chain_provider,orats_diagnostics,orats_option_chain_loader}.py`, `chakraops/app/core/options/v2/{csp,cc}_chain_v2.py`.
- MODIFIED `chakraops/app/core/eligibility/providers/orats_daily_provider.py`, `chakraops/app/core/eval/universe_evaluator.py`, `chakraops/app/core/data/symbol_snapshot_service.py`, `chakraops/app/core/journal/alerts.py`.
- MODIFIED `chakraops/app/api/{data_health,copilot,diagnostics,server}.py`.
- NEW `chakraops/tests/test_r340_orats_redaction_complete.py`.

Phase 3 — live sector enforcement:
- MODIFIED `chakraops/app/core/decision_engine/live_service.py` — map symbol sector + symbol/sector exposure from portfolio/artifact data; safe BLOCKED policy when sector unavailable.
- MODIFIED `chakraops/app/core/decision_engine/sizing.py` — enforce profile sector caps; `SECTOR_DATA_UNAVAILABLE` BLOCKED policy for incremental CSP/share-buy; `SECTOR_DATA_UNAVAILABLE_EXISTING_POSITION` for owned-share covered calls.
- NEW `chakraops/tests/test_r340_sector_enforcement.py`.

Phase 4 — rendered canonical cutover (Dashboard + Today):
- NEW `frontend/src/components/AuthoritativeRecommendations.tsx` — shared canonical primary renderer (actionable/WATCH/BLOCKED/STAY_IN_CASH, profile, manual-only, freshness, provider health, event availability, safe reason labels, per-suggestion + combined capital, deployable cash, additivity, combined-capital warning).
- MODIFIED `frontend/src/pages/DashboardPage.tsx`, `frontend/src/pages/TodayPage.tsx` — render canonical as primary; legacy demoted to collapsed “Diagnostics — non-authoritative legacy output”.
- MODIFIED `frontend/src/api/{queries.ts,types.ts}` as needed (safe reason-label map).
- MODIFIED `frontend/src/pages/DashboardPage.test.tsx`, `frontend/src/pages/TodayPage.test.tsx`; NEW page-level canonical-render tests.

Phase 5 — Symbol Diagnostics:
- MODIFIED `frontend/src/pages/SymbolDiagnosticsPage.tsx` — render `canonical_decision` primary; legacy explanatory; UNAVAILABLE/NOT-EVALUATED state + Recompute; never expose raw FAIL_/WARN_/PASS.
- MODIFIED `frontend/src/api/{queries.ts,types.ts}` — `canonical_decision`/`canonical_status` types; 404 handling.
- MODIFIED/NEW `frontend/src/pages/SymbolDiagnosticsPage.*.test.tsx`.

Phase 6 — frontend correctness:
- MODIFIED `frontend/src/pages/{UniverseAdminPage,PortfolioPage,BacktestPage,JournalPage,ReportsPage}.tsx` — remove `<TableRow>` nested in `<TableHeader>` (fix `<tr>`-in-`<tr>`).
- MODIFIED `frontend/src/pages/BacktestPage.tsx` — `SIMULATION — NOT A LIVE RECOMMENDATION` label.
- MODIFIED `frontend/src/pages/PositionsPage.tsx` — bounded pagination.
- MODIFIED `frontend/src/layout/Sidebar.tsx` (+ `Sidebar.test.tsx`) — logical nav grouping.
- NEW/MODIFIED component tests as needed.

Governance/evidence (authorized for edit): `docs/ai/releases/R34.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`, `docs/ai/releases/R32.0/{STATUS,TOOL_LOG}.md`, `docs/ai/PROGRAM_STATUS.md`, `docs/master/CURRENT_STATE.md`, `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`, `chakraops/docs/releases/{R34.0_requirements,R34.0_release_notes,RELEASE_CHECKLIST}.md`, `out/verification/R34.0/*` (local ignored).

### Implementation reconciliation (2026-06-22c) — as-built within authorized scope
- Phase 5 backend: `canonical_decision`/`canonical_status`/`decision_source`/`active_profile` are populated by a new helper `_canonical_decision_for_symbol` in `chakraops/app/api/server.py` (already an authorized ORATS-redaction path; fail-closed UNAVAILABLE on any error). NEW test `frontend/src/pages/SymbolDiagnosticsPage.canonical.test.tsx`.
- Phase 6 DOM fix: implemented centrally in the shared `frontend/src/components/ui/Table.tsx` (`TableHeader` no longer double-wraps `<tr>`), which fixes every shared-table consumer (Portfolio, Positions, Reports, Backtest, Journal, Universe Admin) without per-page edits. NEW test `frontend/src/components/ui/Table.dom.test.tsx`.
- Phase 6 new tests: `frontend/src/pages/BacktestPage.simulation.test.tsx`, positions-pagination cases in `frontend/src/pages/PositionsPage.test.tsx`, nav-grouping case in `frontend/src/layout/Sidebar.test.tsx`.
- Frontend reason-label safety: NEW `frontend/src/utils/reasonLabels.ts` (translates canonical reason/risk codes to safe operator labels; strips raw FAIL_/WARN_/PASS).
- Evidence (local ignored): `out/verification/R34.0/{notes,changed_files,weekly_refresh_transaction,secret_redaction,sector_enforcement,rendered_canonical_cutover,frontend_uat_plan}.md`, `{backend,frontend,build}.log`.

### Approved for post-R35 enhancement (NOT required for R34)
Drag-and-drop dashboard customization; broad visual redesign; physical deletion of all legacy modules; extensive bundle architecture beyond low-risk improvements; advanced multi-user database architecture.

### Operator authorization waiver — commit 50aa600 (2026-06-22d)

The operator explicitly accepts the historical exact-path deviation in commit `50aa600`
(`R34.0: complete rendered canonical cutover and product hardening`). This is a
**documented waiver**, not retroactive authorization and **not permission to repeat the
pattern**. Any future path discovered after packet authorization still requires a packet
update committed before edit.

Codex final R34 review: **BLOCKED** on refresh integrity, remaining ORATS redaction,
authorization reconciliation, and generated-file hygiene. Claude final R34 review:
APPROVED WITH NON-BLOCKING NOTES. Cowork real-browser UAT: PASS WITH NOTES.

### Complete as-built path list — commit 50aa600 (exact)

**Backend — modified**
- `chakraops/app/api/copilot.py`
- `chakraops/app/api/data_health.py`
- `chakraops/app/api/diagnostics.py`
- `chakraops/app/api/server.py`
- `chakraops/app/api/ui_routes.py`
- `chakraops/app/core/decision_engine/engine.py`
- `chakraops/app/core/decision_engine/gates.py`
- `chakraops/app/core/decision_engine/live_service.py`
- `chakraops/app/core/decision_engine/sizing.py`
- `chakraops/app/core/eligibility/providers/orats_daily_provider.py`
- `chakraops/app/core/options/orats_diagnostics.py`
- `chakraops/app/core/options/providers/orats_client.py`
- `chakraops/app/core/options/providers/orats_provider.py`
- `chakraops/app/core/orats/orats_client.py`
- `chakraops/app/core/orats/orats_core_client.py`
- `chakraops/app/core/orats/orats_equity_quote.py`
- `chakraops/app/core/universe/refresh_history_store.py`
- `chakraops/app/core/universe/universe_overrides.py`
- `chakraops/app/core/universe/weekly_refresh.py`

**Backend — new**
- `chakraops/app/core/universe/refresh_lock.py`
- `chakraops/tests/test_r340_orats_redaction_complete.py`
- `chakraops/tests/test_r340_sector_enforcement.py`
- `chakraops/tests/test_r340_weekly_refresh_transaction.py`

**Backend — modified tests**
- `chakraops/tests/test_r340_live_cutover.py`
- `chakraops/tests/test_r340_missing_cash_sector.py`

**Frontend — modified**
- `frontend/src/api/queries.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/ui/Table.tsx`
- `frontend/src/layout/Sidebar.test.tsx`
- `frontend/src/layout/Sidebar.tsx`
- `frontend/src/pages/BacktestPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/PositionsPage.test.tsx`
- `frontend/src/pages/PositionsPage.tsx`
- `frontend/src/pages/SymbolDiagnosticsPage.tsx`
- `frontend/src/pages/TodayPage.tsx`

**Frontend — new**
- `frontend/src/components/AuthoritativeRecommendations.tsx`
- `frontend/src/components/ui/Table.dom.test.tsx`
- `frontend/src/pages/BacktestPage.simulation.test.tsx`
- `frontend/src/pages/DashboardPage.canonical.test.tsx`
- `frontend/src/pages/SymbolDiagnosticsPage.canonical.test.tsx`
- `frontend/src/pages/TodayPage.canonical.test.tsx`
- `frontend/src/utils/reasonLabels.ts`

**Explicit waiver-reconciled paths (authorized in packet intent, delivered in 50aa600)**
- `chakraops/app/core/decision_engine/engine.py` — sector_gate integration
- `chakraops/app/core/decision_engine/gates.py` — `sector_gate`
- `frontend/src/components/ui/Table.tsx` — shared-table DOM fix (centralized)
- `frontend/src/components/ui/Table.dom.test.tsx`
- `frontend/src/utils/reasonLabels.ts`

**Frontend test paths (exact, all new in 50aa600)**
- `frontend/src/components/ui/Table.dom.test.tsx`
- `frontend/src/pages/BacktestPage.simulation.test.tsx`
- `frontend/src/pages/DashboardPage.canonical.test.tsx`
- `frontend/src/pages/SymbolDiagnosticsPage.canonical.test.tsx`
- `frontend/src/pages/TodayPage.canonical.test.tsx`
- `frontend/src/layout/Sidebar.test.tsx` (nav-grouping case added)

**Generated-file hygiene note (Codex finding)**
- `frontend/tsconfig.tsbuildinfo` was modified in 50aa600 — tracked generated artifact;
  remediation pass will untrack + ignore (Fix 4).

**Docs/governance (50aa600)**
- `docs/ai/PROGRAM_STATUS.md`, `docs/master/CURRENT_STATE.md`, `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`
- `docs/ai/releases/R32.0/TOOL_LOG.md`, `docs/ai/releases/R34.0/{RELEASE_PACKET,STATUS,TOOL_LOG,notes}.md`
- `chakraops/docs/releases/{R34.0_requirements,R34.0_release_notes,RELEASE_CHECKLIST}.md`

### Final operational-integrity remediation (2026-06-22d) — exact authorized paths

Starting commit: `50aa600`. Docs-only waiver commit precedes all source edits.

Fix 1 — refresh journal corruption and history safety:
- MODIFIED `chakraops/app/core/universe/refresh_lock.py` — strict journal read/validate/clear; fail-loud on corruption
- MODIFIED `chakraops/app/core/universe/refresh_history_store.py` — strict history read for append/transaction; preserve file on failure
- MODIFIED `chakraops/app/core/universe/weekly_refresh.py` — recovery/clear verification; critical errors on journal/history corruption
- MODIFIED `chakraops/tests/test_r340_weekly_refresh_transaction.py` — corruption/recovery cases
- NEW `chakraops/tests/test_r340_refresh_journal_history_integrity.py`

Fix 2 — ownership-safe cross-process lock:
- MODIFIED `chakraops/app/core/universe/refresh_lock.py` — lock metadata (lock_id, pid, hostname, created_at, process_start); ownership-verified release; no age-only steal
- NEW `chakraops/tests/test_r340_refresh_lock_ownership.py` — subprocess lock tests, PID-reuse, timeout, live-lock retention

Fix 3 — complete downstream ORATS sanitization:
- MODIFIED `chakraops/app/core/options/orats_chain_provider.py`
- MODIFIED `chakraops/app/core/options/orats_option_chain_loader.py`
- MODIFIED `chakraops/app/core/options/orats_chain_pipeline.py` (stage2_trace error redaction if needed)
- MODIFIED `chakraops/tests/test_r340_orats_redaction_complete.py` and/or NEW `chakraops/tests/test_r340_orats_redaction_downstream.py`

Fix 4 — generated-file and evidence hygiene:
- REMOVE FROM GIT `frontend/tsconfig.tsbuildinfo` (if generated)
- MODIFIED `.gitignore` — add `*.tsbuildinfo` or `frontend/tsconfig.tsbuildinfo`
- Evidence cleanup under `out/verification/R34.0/` (ignored; latest logs only)

Governance/evidence (authorized): `docs/ai/releases/R34.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`, `docs/ai/PROGRAM_STATUS.md`, `out/verification/R34.0/*` (ignored).

Any additional tracked path requires operator approval and a packet update committed before that path is edited.

### Final lock-race and test-validity remediation (2026-06-22f) — exact authorized paths

Starting commit: `662b81e`. Docs-only authorization commit precedes all source edits. Codex final targeted review **BLOCKED** on unsafe stale-lock reclamation race, invalid unreadable-journal test (patches `Path.read_text` instead of production `open`), and tautological ORATS stage2_trace test. R35 must not start until these blockers close.

Fix 1 — replace unsafe stale-lock reclamation with OS-native file lock:
- MODIFIED `chakraops/app/core/universe/refresh_lock.py` — `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows); hold fd for entire critical section; timeout/retry; release OS lock on fd; never unlink/reclaim based on age or inferred process death; optional metadata for diagnostics only
- MODIFIED `chakraops/tests/test_r340_refresh_lock_ownership.py` — real Windows-compatible `multiprocessing` spawn tests (mutual exclusion, long holder not displaced, timeout, process death releases lock, subsequent acquire, no lock theft on unknown liveness); must not skip Windows subprocess tests

Fix 2 — correct unreadable-journal test to exercise production `open` path:
- MODIFIED `chakraops/tests/test_r340_refresh_journal_history_integrity.py` — patch `builtins.open` for journal path; assert `RefreshJournalError`, journal not absent, no overlay/history mutation, file intact; retain malformed JSON, incomplete fields, history corruption, journal-clear failure tests

Fix 3 — exercise real ORATS pipeline error paths (not direct `redact_secrets()`):
- MODIFIED `chakraops/tests/test_r340_orats_redaction_complete.py` — drive active chain-provider worker, delayed pipeline, loader, stage-two trace, nested `RequestException` paths; assert fake token absent from logs, exceptions, result.error, trace fields; useful endpoint/status/classification preserved

Governance/evidence (authorized for edit):
- `docs/ai/releases/R34.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`
- `docs/ai/PROGRAM_STATUS.md` (if status summary update required)
- `out/verification/R34.0/{final_lock_race_remediation,windows_multiprocess_lock,journal_test_validity,orats_active_path_redaction,backend,frontend,build}.md|.log` (local ignored evidence)

Any additional tracked path requires operator approval and a packet update committed before that path is edited.

### Final ORATS provider-error patch (2026-06-23) — exact authorized paths

Starting commit: `b860a73`. Docs-only authorization commit precedes all source edits. Claude final targeted review **APPROVED**; Codex final targeted review **BLOCKED** on remaining ORATS provider logging/tests and evidence Windows lock-test count mismatch (6 collected, not 7); Cowork real-browser R34 UAT **PASS WITH NOTES**. R35 must not start until these blockers close.

Fix 1 — sanitize every active provider expiration/chain path:
- MODIFIED `chakraops/app/core/options/orats_chain_provider.py` — `_get_expirations_delayed`, `_get_expirations_live`, `_get_chain_live`, worker/batch failures, delayed pipeline result/error/trace paths; use `redact_secrets` / `safe_provider_error`; no raw `str(e)` in logs or returned errors

Fix 2 — real-path provider redaction tests:
- MODIFIED `chakraops/tests/test_r340_orats_redaction_complete.py` — drive `_get_expirations_delayed`, `_get_expirations_live`, `_get_chain_live`, worker/batch failure, returned result/error paths with fake secrets in exception/URL/header/body; caplog assertions

Fix 3 — correct evidence lock-test count:
- MODIFIED `docs/ai/releases/R34.0/{STATUS,TOOL_LOG}.md`
- MODIFIED `chakraops/tests/test_r340_refresh_lock_ownership.py` — Windows spawn timing sync (`Event` gate) so waiter starts while holder still holds; truthful count 6 collected
- Evidence (ignored): `out/verification/R34.0/{windows_multiprocess_lock,final_lock_race_remediation,orats_active_path_redaction,backend,frontend,build}.md|.log`

Governance (authorized): `docs/ai/releases/R34.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`, `out/verification/R34.0/*` (ignored)

Any additional tracked path requires operator approval and a packet update committed before that path is edited.

### Operator authorization waiver — authorization-order deviation (2026-06-23)

The operator explicitly accepts the authorization-order deviation involving
`chakraops/tests/test_r340_refresh_lock_ownership.py` in commit `2c41ba2`.

**Facts (accurate record):**

1. Commit `3808f66` was the documentation-only authorization commit for the final ORATS provider-error patch.
2. Commit `2c41ba2` modified `chakraops/tests/test_r340_refresh_lock_ownership.py`.
3. The exact path was added to the packet in the same implementation commit (`2c41ba2`) rather than in the preceding authorization commit (`3808f66`).
4. This violated the program's authorization-before-edit rule.
5. The operator accepts this single historical deviation because:
   - the changed file was test-only
   - the change synchronized the Windows spawn multiprocessing test using an `Event` gate
   - it did not alter production lock behavior
   - it remained within the already approved lock-test correction intent
   - six Windows lock tests passed
   - full backend, frontend, and build gates passed
6. This waiver:
   - is **not** retroactive authorization
   - does **not** erase or hide the process deviation
   - does **not** create permission to repeat the pattern
   - applies only to this exact file and commit (`2c41ba2` / `test_r340_refresh_lock_ownership.py`)
7. All future paths must still be authorized in a committed packet **before** modification.

**Closure state (2026-06-23):** Claude closure verdict **APPROVED WITH NON-BLOCKING NOTES**; Codex closure verdict **BLOCKED only on authorization ordering** — technical provider-redaction findings closed; R34 implementation and technical validation complete; final Codex governance confirmation pending.

## Forbidden paths and actions


- changing strategy mathematics without R33 packet update
- broker order forms
- automated execution
- cosmetic redesign without workflow value
- destructive data migration without backup


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Define one-page ownership map.
2. Consolidate dashboard/today/analysis flows.
3. Consolidate positions/portfolio/wheel flows.
4. Separate universe administration from data health.
5. Harden backtest assumptions and labels.
6. Implement retention/reporting schema.
7. Fix known DOM nesting and high-value bundle issues.
8. Add migration, API, component, and end-to-end tests.



## Mandatory baseline gates

Before `DONE`, run exactly:

```powershell
cd chakraops
python -m pytest tests -q --tb=short

cd ..\frontend
npm run test -- --run
npm run build
```

Store local evidence under:

`out/verification/R34.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Database migration up/down or documented forward-only recovery.
- Backtest deterministic fixture checks.
- Reports reconcile with journal/position data.
- UI clearly labels delayed/live/simulated/historical states.
- No hidden duplicate primary workflow remains.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R34.0: Unified Product Experience, Backtest, Database, and Reporting`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
