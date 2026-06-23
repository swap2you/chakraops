# ChakraOps — Startup and Shutdown Runbook (R35.0)

Repository root: `C:\Development\Workspace\ChakraOps-dev\chakraops`

## Daily startup

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\start_chakraops.ps1
```

- Verifies Python and Node
- Loads ignored `chakraops\.env` (values never printed)
- Starts backend (`http://127.0.0.1:8000`) and frontend (`http://127.0.0.1:5173`)
- Scheduler remains **disabled** unless `CHAKRAOPS_SCHEDULER_ENABLED=true`

## Daily shutdown

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\stop_chakraops.ps1
```

## Health check

```powershell
.\scripts\health_check_chakraops.ps1
```

## Enable scheduler (operator confirmation required)

Set environment variable and restart, or use API:

```
POST /api/operations/scheduler/enable?confirm=ENABLE
```

Individual jobs also require `CHAKRAOPS_JOB_<ID>_ENABLED=true`.

## Disable scheduler

```
POST /api/operations/scheduler/disable
```

## Manual job run

```
POST /api/operations/jobs/{job_id}/run
```

No job submits broker orders. Stay in Cash is valid.
