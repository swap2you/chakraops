# ChakraOps — Troubleshooting Runbook (R35.0)

Repository: `C:\Development\Workspace\ChakraOps-dev\chakraops`

**Do not use** the stale path `C:\Development\Workspace\ChakraOps`.

See also: [RUNBOOK_EXECUTION.md](RUNBOOK_EXECUTION.md) (golden path, sanity script), [RUNBOOK_STARTUP_SHUTDOWN.md](RUNBOOK_STARTUP_SHUTDOWN.md) (start/stop scripts).

---

## Dedicated ports (always use these)

| Service | Port | URL |
|---------|------|-----|
| Backend API | **18800** | http://127.0.0.1:18800 |
| Frontend UI | **18873** | http://127.0.0.1:18873 |

Source of truth: `scripts/chakraops_ports.ps1`, `chakraops/app/core/chakraops_ports.py`, `frontend/.env.development`.

**Always open the UI at `127.0.0.1:18873`, not `localhost:5173` or `localhost:8000`.**

---

## Quick diagnostic flow

Run these in order when something looks wrong:

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops

# 1) Correct checkout?
git rev-parse --show-toplevel
# Expected: ...\ChakraOps-dev\chakraops

# 2) Ports free?
netstat -ano | findstr ":18800"
netstat -ano | findstr ":18873"

# 3) Backend reachable (direct — bypasses Vite)?
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/operations/status" -UseBasicParsing | Select-Object StatusCode

# 4) Vite proxy working?
Invoke-WebRequest -Uri "http://127.0.0.1:18873/api/healthz" -UseBasicParsing | Select-Object StatusCode

# 5) Scripted health check
.\scripts\health_check_chakraops.ps1
```

| Step | Expected | If it fails |
|------|----------|-------------|
| 3 healthz | 200 | Backend not running or wrong port — see [Backend unreachable](#backend-unreachable) |
| 3 operations/status | 200 JSON | Same as above |
| 4 via proxy | 200 | Vite not running or proxy misconfigured — see [UI Failed to load](#ui-failed-to-load-universe-or-other-pages) |
| 5 health script | exit 0 | Read script output; restart with `start_chakraops.ps1` |

---

## UI: "Failed to load universe" (or other pages blank / red error)

**Symptom:** Universe (or Dashboard) shows *Failed to load universe.* or similar; browser Network tab shows `/api/ui/universe` failing.

### Cause A — Wrong server (most common on Windows)

Another app (often **Docker**) listens on `localhost:8000` via IPv6 (`::1`). If Vite or the browser uses `localhost` instead of `127.0.0.1`, requests hit the wrong process and return **404**.

**Fix:**

1. Use ChakraOps dedicated ports only (`18800` / `18873`).
2. Confirm Vite proxy in **both** `frontend/vite.config.ts` and `frontend/vite.config.js` points to `http://127.0.0.1:18800` (Vite may load the `.js` file).
3. Restart frontend after any config change.
4. Open **http://127.0.0.1:18873/universe** (not `localhost:5173`).

**Verify:**

```powershell
# Should be 200 (ChakraOps)
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/universe" -UseBasicParsing -TimeoutSec 120 | Select-Object StatusCode

# Should be 200 via proxy
Invoke-WebRequest -Uri "http://127.0.0.1:18873/api/ui/universe" -UseBasicParsing -TimeoutSec 120 | Select-Object StatusCode
```

### Cause B — Backend not running

Start or restart:

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\stop_chakraops.ps1
.\scripts\start_chakraops.ps1
```

### Cause C — UI_API_KEY mismatch

If `UI_API_KEY` is set in `chakraops/.env`, the frontend must send the same value as `VITE_UI_KEY` in `frontend/.env` (or unset both for local dev).

Symptom: Network tab shows **401** on `/api/ui/*`.

### Cause D — Slow first load (not a failure)

`/api/ui/universe` with a full 171-symbol artifact can take **60–90 seconds** on first request (rebuilds per-symbol diagnostics). Wait for the request to complete; do not assume timeout unless the browser aborts.

### Cause E — No decision artifact

Run evaluation first:

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out
```

Confirm `[STORE] Canonical decision store path:` at backend startup points to your repo `out/decision_latest.json`.

---

## Backend unreachable

```powershell
# Who owns 18800?
Get-NetTCPConnection -LocalPort 18800 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)" } |
  Select-Object ProcessId, CommandLine
```

- **No listener** — start backend: `.\scripts\start_chakraops.ps1` or manual uvicorn on `--host 127.0.0.1 --port 18800`.
- **Wrong command line** (not uvicorn / wrong repo) — `.\scripts\stop_chakraops.ps1`, then restart from `ChakraOps-dev`.
- **Port in use by another app** — change ports via env (`CHAKRAOPS_BACKEND_PORT`, `CHAKRAOPS_FRONTEND_PORT`) or free the port; do not kill unrelated PIDs blindly.

---

## Stale checkout / wrong server

1. Confirm path: `C:\Development\Workspace\ChakraOps-dev\chakraops`
2. `git rev-parse --short HEAD` — compare with expected program commit
3. Stop old processes: `.\scripts\stop_chakraops.ps1`
4. Restart: `.\scripts\start_chakraops.ps1`
5. If you previously used `C:\Development\Workspace\ChakraOps`, sync port config from `ChakraOps-dev` or switch checkout entirely

---

## Port conflict with other apps

ChakraOps intentionally avoids **8000** and **5173** (Docker, Vite defaults, many Python tutorials).

If **18800** or **18873** is taken:

```powershell
netstat -ano | findstr ":18800"
netstat -ano | findstr ":18873"
```

Override before start (all layers must agree):

```powershell
$env:CHAKRAOPS_BACKEND_PORT = "18801"
$env:CHAKRAOPS_FRONTEND_PORT = "18874"
```

Update `frontend/.env.development` or restart via `start_chakraops.ps1` after editing `scripts/chakraops_ports.ps1`.

---

## ORATS unavailable

- Check token present (boolean only): `GET http://127.0.0.1:18800/api/operations/status`
- Run provider health job manually: `POST http://127.0.0.1:18800/api/operations/jobs/provider_health/run`
- Do not enable silent fallback providers

---

## Stale data / blocked decisions

- Run EOD refresh after market close
- Verify freshness via data-reliability endpoints
- Stay in Cash is valid when gates block

---

## Corrupted job run state

- Inspect `out/job_runs.jsonl`
- Recovery job runs on startup automatically
- Re-run failed jobs manually

---

## Scheduler not firing

- Confirm `CHAKRAOPS_SCHEDULER_ENABLED=true`
- Confirm per-job env var enabled with `confirm=ENABLE` via API
- Legacy schedulers require separate `CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED=true`

---

## Browser DevTools checklist

1. **Network** — filter `api/ui`; note status code (404 → wrong server; 401 → UI key; 500 → backend error body)
2. **Console** — CORS errors → backend `UI_CORS_ORIGINS` must include `http://127.0.0.1:18873`
3. Compare direct vs proxy URLs above

---

## Log collection

| Source | Location |
|--------|----------|
| Backend | uvicorn window / terminal running `start_chakraops.ps1` |
| Frontend | Vite dev server window |
| Job runs | `out/job_runs.jsonl` |
| Notifications | `out/notifications.jsonl` |
| Process ownership | `out/process_ownership.json` |
