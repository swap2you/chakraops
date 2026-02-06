# Scheduling and Run Lifecycle (Phase 5)

This document describes how evaluation runs are scheduled, how overlapping runs are prevented, how run state is persisted, and how the UI reflects running and prior runs.

## Scheduler cadence

- **Config:** `UNIVERSE_EVAL_MINUTES` (environment variable). Default: `15`. Allowed range: `1`–`120`.
- **Recommended values:** `15`, `30`, or `60` minutes depending on how often you want fresh evaluation.
- The background scheduler runs in a daemon thread and triggers evaluation every `UNIVERSE_EVAL_MINUTES` minutes **only when market phase is OPEN**. Outside market hours, the scheduled trigger is skipped.
- No deployment or cron is required in this phase; the scheduler runs inside the API process.

## Preventing overlapping runs

- **File lock:** A single lock file is used: `out/evaluations/run.lock`. Creating it is exclusive (cross-platform: create-only, so if the file already exists we do not overwrite).
- **Acquire before run:** Both the **API** (POST /api/ops/evaluate-now) and the **scheduler** (via `trigger_evaluation`) call `acquire_run_lock(run_id, started_at)` before starting. If the lock cannot be acquired (file already exists and not stale), the run is **skipped** and a message is logged (e.g. "Evaluation already in progress").
- **Release after run:** On success or failure, `release_run_lock()` is called so the next run can proceed.
- **Stale lock:** If the lock file is older than **2 hours** (`RUN_LOCK_STALE_SEC`), it is treated as stale (e.g. process crashed) and is removed when checking status or on startup. This avoids being stuck forever if the server died during a run.

## Persisted run state

- **States:** `RUNNING`, `COMPLETED`, `FAILED`.
- **When a run starts:**  
  - Lock file is created with `run_id` and `started_at`.  
  - A minimal run file is written with `status=RUNNING`, `started_at`, `symbols=[]`, so the run appears in History and has a clear start time.
- **When a run completes successfully:**  
  - Full run is saved (symbols, counts, etc.) with `status=COMPLETED`, `completed_at`, `duration_seconds`.  
  - **Latest pointer** (`out/evaluations/latest.json`) is updated to this run **only** when status is COMPLETED. Dashboards read from this pointer, so they always see the **last completed** run by default.
- **When a run fails:**  
  - `save_failed_run(run_id, reason, error, started_at)` persists a run file with `status=FAILED`, `completed_at`, `duration_seconds`, `error_summary`.  
  - The latest pointer is **not** updated, so the last COMPLETED run remains the one shown on dashboards.

All run files are stored under `out/evaluations/` as `{run_id}.json`. The data completeness report is written as `{run_id}_data_completeness.json` (Phase 4).

## UI behavior

- **RUNNING banner:** When a run is in progress, the Dashboard (and any view that polls evaluation status) shows a clear banner: "Evaluation run in progress" with the current run id. The "Run evaluation now" button is disabled. Status comes from the **persistent** lock (GET /api/view/evaluation/status/current), so even after a refresh or from another tab, the UI shows running if the lock file exists.
- **Dashboards read last COMPLETED run:**  
  - GET /api/view/evaluation/latest returns the run pointed to by `latest.json`, and only returns full data (symbols, counts) when that run’s `status` is `COMPLETED`. If the pointed run is RUNNING or FAILED, the API returns `has_completed_run: false` and no symbols, so dashboards do not show incomplete data.
- **History and prior runs:**  
  - The History page lists all runs (RUNNING, COMPLETED, FAILED) with status, started_at, duration, eligible/holds, etc.  
  - **View run:** Each run has a "View run" link that opens the Dashboard with that run’s data (e.g. `/dashboard?run_id=eval_...`). The Dashboard shows a "Viewing prior run" notice and a "Back to latest" link to return to the default (last completed) run.

## Windows and Linux

- Lock and run files use the same paths and JSON format on both platforms. No Redis or external service is required. The lock is a normal file; creation is exclusive so only one process can hold it at a time.

## Summary

| Item | Detail |
|------|--------|
| Cadence | `UNIVERSE_EVAL_MINUTES` (default 15), range 1–120 |
| Overlap guard | File lock `out/evaluations/run.lock`; skip and log if already running |
| Run states | RUNNING (stub at start), COMPLETED, FAILED |
| Latest pointer | Updated only for COMPLETED runs; dashboards use this by default |
| UI running | Banner when lock exists; button disabled |
| Prior runs | History lists all runs; "View run" loads that run on Dashboard |
