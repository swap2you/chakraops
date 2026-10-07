# ChakraOps — Scheduler Operations Runbook (R35.0)

Repository: `C:\Development\Workspace\ChakraOps-dev\chakraops`

## Defaults (disabled by default)

| Control | Default | Meaning |
|---------|---------|---------|
| `CHAKRAOPS_SCHEDULER_ENABLED` | `false` | Master poll thread |
| `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED` | `false` | Legacy in-process schedulers |
| `CHAKRAOPS_JOB_*_ENABLED` | `false` | Each recurring job |

Recurring jobs do **not** run until explicitly enabled by the operator after UAT.

## Safe status inspection

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
python -c "from app.core.operations.scheduler_service import scheduler_status; import json; print(json.dumps(scheduler_status(), indent=2))"
```

Or open **System Diagnostics → Operations** in the UI (`http://127.0.0.1:18873/system-diagnostics`).

Inspect `out/job_runs.jsonl` for recent runs (read-only).

## Enable request without confirmation (rejected)

API enable endpoints require `confirm=ENABLE`. Requests without it are rejected.

Do not set environment variables to `true` until operational UAT approves enablement.

## Explicit enable procedure (post-UAT only)

1. Complete Windows live operational UAT.
2. Set only the jobs required: e.g. `CHAKRAOPS_JOB_BACKUP_ENABLED=true`.
3. Set `CHAKRAOPS_SCHEDULER_ENABLED=true` only when ready for scheduled polling.
4. Restart via `scripts\start_chakraops.ps1` (scheduler forced disabled on startup script by default).
5. Verify status shows `master_enabled: true` and intended jobs enabled.

## Immediate disable procedure

```powershell
$env:CHAKRAOPS_SCHEDULER_ENABLED = "false"
# unset or set false for each CHAKRAOPS_JOB_*_ENABLED
```

Restart backend or call stop/start scripts. Poll thread stops; no new scheduled executions.

## Restart behavior

- Recovery reconciliation runs once on startup (`recovery_reconciliation` job).
- Scheduled occurrences use atomic claim — completed slots are not re-run after restart.
- Missed windows while down are **not** backfilled; use manual **Run now**.

## Manual safe jobs (operator-initiated)

Safe for manual invocation via Operations panel or API:

- `provider_health`
- `backup`
- `recovery_reconciliation` (startup)

Use **Run now** with `trigger=manual` — separate from scheduled occurrence identity.

## Prohibited live-UAT jobs

Do not enable or run on a live UAT pass without explicit operator approval:

- `decision_generation` (advisory batch)
- `eod_data_refresh` (market data mutation)
- `weekly_universe_refresh` (universe mutation)
- `nightly_reports`

## Occurrence dedupe and overlap protection

- Each scheduled slot claimed atomically (`CLAIMED` → `COMPLETED`).
- OS-native cross-process locks prevent overlapping job runs.
- Second process receives `ALREADY_CLAIMED` or `ALREADY_COMPLETED`.

## Recovery reconciliation

On startup, interrupted runs may be marked `RECOVERED` in `out/job_runs.jsonl`. Does not execute trades or broker actions.

## Emergency shutdown

```powershell
C:\Development\Workspace\ChakraOps-dev\chakraops\scripts\stop_chakraops.ps1
```

Sets scheduler off; terminates owned backend/frontend PIDs only.

## No broker or order execution

ChakraOps R35 operations stack has **no** broker routing, order placement, or automatic trade execution path. Jobs refresh data, generate advisory artifacts, backup state, and emit notifications only. Manual execution remains operator-only per `RUNBOOK_EXECUTION.md`.
