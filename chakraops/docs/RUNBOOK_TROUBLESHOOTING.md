# ChakraOps — Troubleshooting Runbook (R35.0)

Repository: `C:\Development\Workspace\ChakraOps-dev\chakraops`

**Do not use** the stale path `C:\Development\Workspace\ChakraOps`.

## Stale checkout / wrong server

1. Confirm path: `C:\Development\Workspace\ChakraOps-dev\chakraops`
2. `git rev-parse --short HEAD` — compare with expected program commit
3. Stop old processes: `.\scripts\stop_chakraops.ps1`
4. Restart: `.\scripts\start_chakraops.ps1`

## ORATS unavailable

- Check token present (boolean only): `GET /api/operations/status`
- Run provider health job manually: `POST /api/operations/jobs/provider_health/run`
- Do not enable silent fallback providers

## Stale data / blocked decisions

- Run EOD refresh after market close
- Verify freshness via data-reliability endpoints
- Stay in Cash is valid when gates block

## Corrupted job run state

- Inspect `out/job_runs.jsonl`
- Recovery job runs on startup automatically
- Re-run failed jobs manually

## Scheduler not firing

- Confirm `CHAKRAOPS_SCHEDULER_ENABLED=true`
- Confirm per-job env var enabled with `confirm=ENABLE` via API
- Legacy schedulers require separate `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true`

## Log collection

- Backend: uvicorn window output
- Frontend: Vite dev server window
- Job runs: `out/job_runs.jsonl`
- Notifications: `out/notifications.jsonl`
