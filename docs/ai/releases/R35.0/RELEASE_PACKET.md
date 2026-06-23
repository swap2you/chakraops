# R35.0 Release Packet — Operations, Scheduling, Recovery, UAT, and Release Readiness

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch. One final PR opens only after R35.0 is complete.

## Risk level

Level 3 — operational reliability and release readiness

## Objective

Make ChakraOps reliable for daily personal use with observable jobs, clear alerts, recovery procedures, validated workflows, and final program handoff.

## Dependencies

R34.0 closed and approved (Claude APPROVED WITH NON-BLOCKING NOTES; Codex APPROVED; Cowork PASS WITH NOTES).

## Scope

Canonical job inventory, unified scheduler (disabled-by-default), job-run persistence and recovery, notifications dedupe, backup/restore, operations dashboard, Windows startup/shutdown runbooks, final R31–R35 handoff. No broker execution. No automatic trade routing.

---

## Phase 0 — governance (2026-06-23)

Starting commit: `902a9cb`. Docs-only authorization precedes all source edits.

---

## Allowed tracked paths — exact (R35 operational readiness)

### Phase 1 — canonical job inventory and registry

- NEW `chakraops/app/core/operations/__init__.py`
- NEW `chakraops/app/core/operations/job_registry.py` — authoritative job definitions (ID, purpose, schedule, lock, retry, notification policy)
- NEW `chakraops/app/core/operations/job_run_store.py` — persisted STARTED/SUCCEEDED/FAILED/SKIPPED/TIMED_OUT/RECOVERED runs
- NEW `chakraops/app/core/operations/job_executor.py` — lock, timeout, bounded retry/backoff, safe error summary
- NEW `chakraops/tests/test_r350_job_registry.py`
- NEW `chakraops/tests/test_r350_job_run_store.py`

### Phase 2–4 — unified scheduler and job wrappers

- NEW `chakraops/app/core/operations/scheduler_service.py` — single scheduler registration; disabled-by-default; idempotent startup; no duplicate registration; uses OS-native lock from `refresh_lock.py`
- NEW `chakraops/app/core/operations/jobs/__init__.py`
- NEW `chakraops/app/core/operations/jobs/weekly_refresh_job.py`
- NEW `chakraops/app/core/operations/jobs/eod_data_refresh_job.py`
- NEW `chakraops/app/core/operations/jobs/decision_generation_job.py`
- NEW `chakraops/app/core/operations/jobs/nightly_reports_job.py`
- NEW `chakraops/app/core/operations/jobs/backup_job.py`
- NEW `chakraops/app/core/operations/jobs/provider_health_job.py`
- NEW `chakraops/app/core/operations/jobs/retention_cleanup_job.py`
- NEW `chakraops/app/core/operations/jobs/recovery_job.py`
- MODIFIED `chakraops/app/api/server.py` — lifespan delegates to `scheduler_service`; legacy in-process schedulers gated/disabled-by-default; no duplicate active registration
- MODIFIED `chakraops/app/core/universe/weekly_refresh.py` — scheduled-job entrypoint wrapper only (no logic change)
- MODIFIED `chakraops/app/core/eval/nightly_evaluation.py` — job-safe entry wrapper
- MODIFIED `chakraops/app/core/eval/eod_chain_snapshot.py` — job-safe entry wrapper
- NEW `chakraops/tests/test_r350_scheduler_safety.py`
- NEW `chakraops/tests/test_r350_job_executor.py`
- NEW `chakraops/tests/test_r350_weekly_refresh_job.py`
- NEW `chakraops/tests/test_r350_decision_generation_job.py`
- NEW `chakraops/tests/test_r350_recovery_interrupted_runs.py`

### Phase 5 — unified notifications

- NEW `chakraops/app/core/operations/notification_service.py` — dedupe, severity, safe labels, recovery notifications
- MODIFIED `chakraops/app/core/alerts/alert_engine.py` — route critical job failures through notification service
- MODIFIED `chakraops/app/api/notifications_store.py` — dedupe key support for job failures
- MODIFIED `chakraops/app/core/notifications/notification_safe_labels.py` — job/source labels as needed
- NEW `chakraops/tests/test_r350_notification_dedupe.py`

### Phase 6 — operations dashboard API and UI

- NEW `chakraops/app/api/operations_routes.py` — jobs list, runs, enable/disable schedule (confirmation token), manual run, ack
- MODIFIED `chakraops/app/api/server.py` — mount operations router
- MODIFIED `chakraops/app/api/ui_routes.py` — consolidate ops status fields if needed
- MODIFIED `chakraops/app/core/system_health.py` — scheduler/job-run/backup fields
- MODIFIED `frontend/src/pages/SystemDiagnosticsPage.tsx` — operations panel (scheduler state, jobs, runs, backup, notifications)
- MODIFIED `frontend/src/api/queries.ts` — operations hooks
- MODIFIED `frontend/src/api/types.ts` — operations types
- NEW `frontend/src/pages/SystemDiagnosticsPage.operations.test.tsx`

### Phase 7 — backup, restore, retention

- NEW `chakraops/app/core/operations/backup_service.py` — SQLite + JSONL + config manifest; excludes secrets
- NEW `chakraops/scripts/backup_chakraops.ps1`
- NEW `chakraops/scripts/verify_backup_chakraops.ps1`
- NEW `chakraops/scripts/list_backups_chakraops.ps1`
- NEW `chakraops/scripts/restore_chakraops_validate.ps1` — temp-path validation only
- NEW `chakraops/scripts/cleanup_expired_backups.ps1`
- MODIFIED `scripts/backup_data.sh` — cross-reference Windows-first path (doc pointer only if needed)
- NEW `chakraops/tests/test_r350_backup_service.py`
- NEW `chakraops/tests/test_r350_retention_cleanup.py`

### Phase 8–9 — runbooks and Windows startup/shutdown

- MODIFIED `chakraops/docs/RUNBOOK_EXECUTION.md` — Windows-first paths under `C:\Development\Workspace\ChakraOps-dev\chakraops`
- NEW `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md`
- NEW `chakraops/docs/RUNBOOK_SCHEDULER.md`
- NEW `chakraops/docs/RUNBOOK_BACKUP_RESTORE.md`
- NEW `chakraops/docs/RUNBOOK_TROUBLESHOOTING.md`
- NEW `scripts/start_chakraops.ps1`
- NEW `scripts/stop_chakraops.ps1`
- NEW `scripts/health_check_chakraops.ps1`
- NEW `chakraops/tests/test_r350_startup_scripts.py` — static/script smoke where testable

### Phase 10 — existing scheduler/notification integration tests (extend only)

- MODIFIED `chakraops/tests/test_ui_r21_5_notifications_slack_scheduler.py` — align with disabled-by-default policy
- MODIFIED `chakraops/tests/test_ui_routes.py` — operations endpoints

### Phase 11 — evidence (ignored local)

- `out/verification/R35.0/*` (all evidence files listed in R35 cursor_build)

### Phase 12 — governance, requirements, release notes, final handoff

- MODIFIED `docs/ai/releases/R35.0/{STATUS,TOOL_LOG,RELEASE_PACKET}.md`
- MODIFIED `docs/ai/PROGRAM_STATUS.md`
- MODIFIED `docs/master/CURRENT_STATE.md`
- MODIFIED `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md` — L-3/L-4/L-5/L-9 disposition
- NEW `chakraops/docs/releases/R35.0_requirements.md`
- NEW `chakraops/docs/releases/R35.0_release_notes.md`
- MODIFIED `chakraops/docs/releases/RELEASE_CHECKLIST.md`
- NEW `docs/ai/FINAL_PROGRAM_HANDOFF_R31_R35.md`
- NEW `docs/ai/FINAL_CHANGED_FILE_INVENTORY_R31_R35.md`
- NEW `docs/ai/FINAL_UNRESOLVED_ISSUES_R31_R35.md`
- NEW `docs/ai/FINAL_GATE_SUMMARY_R31_R35.md`
- NEW `docs/ai/FINAL_ORATS_VALIDATION_R31_R35.md`
- NEW `docs/ai/FINAL_UAT_PLAN_R31_R35.md`
- NEW `docs/ai/FINAL_PR_DESCRIPTION_R31_R35.md`

Any additional tracked path requires operator approval and a packet update committed before that path is edited.

## Forbidden paths and actions

- public unauthenticated hosting
- automatic broker actions / order routing / trade execution
- write-capable brokerage integration
- secrets in repository, logs, or evidence
- enabling every existing job without explicit operator enablement
- destructive live restore during automated tests
- modifying, printing, or committing ignored local ORATS `.env`

Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- ORATS sole active options provider.
- Stay in Cash remains valid.

## Mandatory baseline gates

```powershell
cd chakraops
python -m pytest tests -q --tb=short

cd ..\frontend
npm run test -- --run
npm run build
```

Evidence: `out/verification/R35.0/`

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge, tag, deploy, or enable schedules by default without operator approval.
