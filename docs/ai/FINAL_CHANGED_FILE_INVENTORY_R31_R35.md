# Final Changed File Inventory — R31–R35

See `out/verification/R35.0/changed_files.md` and per-milestone release notes under `chakraops/docs/releases/`.

R35.0 primary additions:
- `chakraops/app/core/operations/` — job registry, scheduler, executor, backup, notifications, job handlers
- `chakraops/app/api/operations_routes.py`
- `chakraops/tests/test_r350_*.py`
- `scripts/start_chakraops.ps1`, `stop_chakraops.ps1`, `health_check_chakraops.ps1`
- `chakraops/docs/RUNBOOK_*.md` (4 runbooks)
- Frontend operations panel on System Diagnostics

### Authorization-order waiver (commit `18aa888`)

The following paths were modified in `18aa888` but not listed in preceding auth commit `6bd7a4e`:

- `chakraops/app/core/operations/job_executor.py` — optional `run_id` parameter
- `chakraops/app/core/operations/job_run_store.py` — optional `run_id` in `start_run`

Operator waiver recorded. Applies only to these two files in `18aa888`; not retroactive; pattern not permitted to repeat.
