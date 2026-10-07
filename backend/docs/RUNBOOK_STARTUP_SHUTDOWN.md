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

Stops only processes recorded for this repo in `out/process_ownership.json`.

**R35.2 hardened stop behavior:**

- Works for both launch forms, including module-form `python -m uvicorn` (which does not carry the repo path in its command line).
- A process is only stopped when it presents **two independent ownership signals** — the recorded PID (or a child of it) **or** a listener on the recorded role port, **and** a matching command identity (`uvicorn`/`python` for backend, `vite`/`npm`/`node` for frontend), plus a PID-reuse age guard.
- **Idempotent:** a second run reports "already stopped" / "nothing to stop" and exits 0. Partial starts stop only the running role.
- **Fail-safe:** ambiguous ownership is refused (never force-killed). A record whose `repo_root` is not this checkout is refused.
- **Never targets port 8000** — Docker (`com.docker.backend` on `:8000`) and unrelated Python/Node processes are left running.

> Note: only stacks started via `start_chakraops.ps1` write an ownership record. A stack started manually (separate backend/frontend terminals) has **no record**, so `stop_chakraops.ps1` reports "nothing to stop" — stop those windows manually (Ctrl+C) or use `start_chakraops.ps1` for a managed lifecycle.

Self-test (local, Windows): `powershell -File scripts\stop_ownership_selftest.ps1` (spawns benign processes on 18811–18813; refuses to run while an ownership record exists).

---

## Pre-UAT "stack up" checklist

Before browser UAT, confirm the stack is actually serving (Cowork R35.1 Note 6):

```powershell
# 1. Start (managed) or confirm manual terminals are up
.\scripts\start_chakraops.ps1

# 2. Confirm listeners on the dedicated ports
Get-NetTCPConnection -LocalPort 18800,18873 -State Listen | Select-Object LocalPort,OwningProcess

# 3. Confirm health before opening the browser
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18873/" -UseBasicParsing | Select-Object StatusCode
```

If either port shows connection-refused, the stack is down — start it before UAT rather than reporting a UI defect.

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
