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

### Staged (later R34 work — NOT claimed complete in this pass)
Phase 5 (rendered visual cutover: Dashboard/Today/Symbol render `authoritative_recommendations.actionable` + separate WATCH/BLOCKED/STAY_IN_CASH) and Phase 6 (full product scope — nav consolidation, portfolio/position experience, universe/data-health UI, backtest engine, journal/retention/reporting, frontend-quality M-13/nested-table) are large and remain remaining R34 scope. They must not be claimed complete until implemented and evidenced. H-5 stays OPEN until Phase 5 page-level cutover tests pass.

Any additional tracked path requires operator approval and a packet update before implementation.

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
