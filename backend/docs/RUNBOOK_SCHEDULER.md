# ChakraOps — Scheduler Runbook (R35.0)

## Defaults

| Control | Default |
|---------|---------|
| `CHAKRAOPS_SCHEDULER_ENABLED` | `false` |
| `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED` | `false` |
| Per-job `CHAKRAOPS_JOB_*_ENABLED` | `false` |

## Canonical jobs

- `weekly_universe_refresh` — Sun 06:00 ET
- `eod_data_refresh` — Mon–Fri after 16:10 ET
- `decision_generation` — Mon–Fri 19:00 ET (advisory only)
- `nightly_reports` — Mon–Fri 19:30 ET
- `backup` — Daily 02:00 ET
- `provider_health` — Every 30 minutes
- `retention_cleanup` — Sun 03:00 ET
- `recovery_reconciliation` — On startup

## Safety

- OS-native cross-process locks prevent overlapping runs
- Bounded retries with exponential backoff
- Persisted run records in `out/job_runs.jsonl`
- No broker execution path

## Missed runs

If the process was down during a scheduled window, use **Run now** via API or wait for the next window after enabling.

## Legacy schedulers

Set `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true` only during transition. Prefer R35 operations jobs.
