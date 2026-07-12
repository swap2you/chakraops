# ChakraOps — Startup and Shutdown Runbook (R35.0)

Repository root: `C:\Development\Workspace\ChakraOps-dev\chakraops`

**Dedicated ports:** backend **18800**, frontend **18873**. See [RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md) if pages fail to load.

---

## Daily startup (recommended)

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\start_chakraops.ps1
```

- Verifies Python and Node
- Confirms ports **18800** and **18873** are free
- Loads ignored `chakraops\.env` (values never printed)
- Starts backend at **http://127.0.0.1:18800** and frontend at **http://127.0.0.1:18873**
- Records PIDs in `out/process_ownership.json` for safe shutdown
- Scheduler remains **disabled** unless `CHAKRAOPS_SCHEDULER_ENABLED=true`

Open the UI: **http://127.0.0.1:18873/dashboard**

---

## Daily shutdown

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\stop_chakraops.ps1
```

Stops only processes recorded for this repo (refuses foreign PIDs).

---

## Health check

```powershell
.\scripts\health_check_chakraops.ps1
```

Or manually:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/operations/status" -UseBasicParsing
```

---

## Manual startup (multi-terminal)

Use when debugging backend or frontend separately.

**Backend** (terminal 1):

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.api.server:app --reload --host 127.0.0.1 --port 18800
```

**Frontend** (terminal 2):

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\frontend
npm run dev
```

Vite reads `frontend/.env.development` for ports; dev server binds **127.0.0.1:18873** and proxies `/api` → **127.0.0.1:18800**.

---

## After startup — smoke checks

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18873/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/universe" -UseBasicParsing -TimeoutSec 120 | Select-Object StatusCode
```

All should return **200**. Universe may take up to ~90s on first load with a full artifact.

---

## Enable scheduler (operator confirmation required)

Set environment variable and restart, or use API:

```
POST http://127.0.0.1:18800/api/operations/scheduler/enable?confirm=ENABLE
```

Individual jobs also require `CHAKRAOPS_JOB_<ID>_ENABLED=true`.

---

## Disable scheduler

```
POST http://127.0.0.1:18800/api/operations/scheduler/disable
```

---

## Manual job run

```
POST http://127.0.0.1:18800/api/operations/jobs/{job_id}/run
```

No job submits broker orders. Stay in Cash is valid.
