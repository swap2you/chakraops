# ChakraOps Execution Runbook

## 1. PURPOSE

This runbook is for **running ChakraOps locally** (backend API + React frontend) with **ORATS as the only options data source**. Use it when you need to:

- Start or restart the full stack cleanly
- Verify that backend and frontend are healthy
- Diagnose startup or connectivity failures

ChakraOps does not use any other options data provider. All options data comes from ORATS Live (api.orats.io/datav2).

### Quick start (backend only, from repo root)

```powershell
cd chakraops
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.api.server:app --reload --port 8000
```

Then open `http://localhost:8000/health` or `http://localhost:8000/api/ops/data-health`. For full stack (frontend) see Section 6.

---

## 2. PREREQUISITES

Verify the following **before** starting backend or frontend. All commands are Windows PowerShell unless noted.

### Python (3.11+)

```powershell
python --version
```

Expected: `Python 3.11.x` or higher (e.g. 3.12, 3.13). If missing or too old, install from python.org or your package manager.

### Node.js (18+)

```powershell
node --version
```

Expected: `v18.x.x` or higher (e.g. v20.x.x LTS). If missing, install from nodejs.org or use nvm-windows.

### npm

```powershell
npm --version
```

Expected: version number (e.g. 10.x). Ships with Node.

### virtualenv (venv)

```powershell
python -m venv --help
```

Expected: help output. Venv is part of the Python standard library (3.3+).

### FastAPI and uvicorn

```powershell
cd chakraops
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import fastapi; import uvicorn; print('OK')"
```

Expected: `OK`. If `ModuleNotFoundError`, run `pip install fastapi uvicorn` (or reinstall from requirements.txt).

---

## 3. ORATS TOKEN (HARDCODED, PRIVATE MODE)

The ORATS API token is **hardcoded** in a single Python file. This is intentional for private, single-user use.

### Token location

**File:** `chakraops/app/core/config/orats_secrets.py`

This is the **only** place the token exists. No config files, no environment variables, no YAML.

### No setup required

- No env vars.
- No config files (e.g. runtime.yaml).
- No dotenv.
- To change the token, edit `app/core/config/orats_secrets.py` only.

**This is NOT production-safe. Refactor before sharing or deploying.**

---

## 4. STOP EVERYTHING (CLEAN RESET)

Before (re)starting, stop all ChakraOps processes and free ports. Run these in order.

### Stop uvicorn (Python backend)

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Stop Vite (Node frontend)

```powershell
Get-Process node -ErrorAction SilentlyContinue | Stop-Process -Force
```

### Kill port 8000 (backend) if still in use

```powershell
netstat -ano | findstr :8000
```

Note the PID in the last column, then:

```powershell
taskkill /PID <PID> /F
```

Or use npx (if Node is installed):

```powershell
npx kill-port 8000
```

### Kill port 5173 (frontend) if still in use

```powershell
netstat -ano | findstr :5173
taskkill /PID <PID> /F
```

Or:

```powershell
npx kill-port 5173
```

---

## 5. BACKEND STARTUP

All commands from repo root. Backend runs from the `chakraops` directory.

### Activate venv and start uvicorn

```powershell
cd chakraops
.\.venv\Scripts\Activate.ps1
uvicorn app.api.server:app --reload --port 8000
```

(First time only: `python -m venv .venv` then `pip install -r requirements.txt`.)

### Expected logs

In the terminal you should see:

- `[CONFIG] ORATS API token loaded (hardcoded, private mode)`
- `===== ORATS BOOT CHECK =====`
- `Token present: True`
- `Probe status: OK`
- `[ROUTES] registered=<number>`
- `===========================`

If you see `Probe status: DOWN`, run the ORATS smoke test (Section 8) and check network or token in `app/core/config/orats_secrets.py`. Do not start the frontend until the backend shows Probe status OK.

---

## 6. FRONTEND STARTUP

Start the frontend **only after** the backend shows ORATS BOOT CHECK with Probe status OK.

```powershell
cd frontend
npm install
npm run dev
```

### Vite proxy

In development, the Vite dev server proxies `/api` to `http://localhost:8000`. The React app uses relative URLs like `/api/ops/data-health`, so requests go to the same origin (e.g. http://localhost:5173) and Vite forwards them to the backend. You do **not** need to set `VITE_API_BASE_URL` for local dev when using this proxy.

Expected: Vite runs on http://localhost:5173; opening the app and switching to LIVE will hit the backend via the proxy.

---

## 7. VERIFICATION CHECKLIST

Use these checks to confirm the stack is healthy. All from a browser or curl, unless noted.

### Backend: data health

Open or curl:

```
http://localhost:8000/api/ops/data-health
```

Expected JSON:

```json
{
  "provider": "ORATS",
  "status": "OK"
}
```

If `status` is not `"OK"`, backend is not ready for the frontend.

### Backend: route manifest

Open or curl:

```
http://localhost:8000/api/ops/routes
```

Expected: JSON array of objects with `path`, `methods`, `name` for each `/api/*` route. Confirms the API is mounted and discoverable.

### Frontend: Refresh Now

1. Open http://localhost:5173
2. Switch to **LIVE** (toggle in the UI)
3. Click **Refresh now**

Expected: Success message or confirmation; no "ORATS DOWN" banner; no 404 errors in the console or network tab.

### Frontend: SPY analysis

1. Go to the Analytics or Symbol Analysis page
2. Enter or select **SPY**
3. Run analysis

Expected: Analysis completes; you see data or a clear "in universe" / options state. No persistent "ORATS DOWN" or 404 for `/api/view/symbol-diagnostics`.

### Expected UI states when healthy

- Data mode: LIVE
- No "ORATS DOWN" banner
- No 404 in browser console for `/api/*`
- Analytics page loads
- Symbol analysis for SPY works

---

## 8. ORATS SMOKE TEST

Run this **before** starting the backend to confirm the ORATS token and network are valid. The smoke script uses the hardcoded token from `app/core/config/orats_secrets.py` (same as the backend). From the `chakraops` directory, with venv activated:

```powershell
cd chakraops
.\.venv\Scripts\Activate.ps1
python scripts/orats_smoke.py SPY
```

### Expected PASS output

- `Endpoint used: https://api.orats.io/datav2/live/strikes`
- `HTTP status: 200`
- `Row count: <positive number>`
- `Sample keys: [ ... ]` (non-empty list)
- `FINAL VERDICT: PASS`

Exit code 0.

### If you see FAIL

- HTTP 401/403: invalid or expired token; edit `app/core/config/orats_secrets.py` and re-run.
- HTTP 429: rate limit; wait and re-run.
- Connection error: check network/firewall/DNS.

Do not start the backend until the smoke test passes.

---

## 9. COMMON FAILURES & FIXES

| Symptom | Root cause | Fix |
|--------|------------|-----|
| 404 on /api/* | Frontend not proxying to backend; or backend not running; or wrong path | Ensure backend is running on 8000. In dev, use Vite proxy (no VITE_API_BASE_URL). Check `/api/ops/routes` in browser to confirm paths. |
| ORATS DOWN banner | Backend probe failed at startup or data-health returns status != OK | Edit token in `app/core/config/orats_secrets.py` if needed. Run `python scripts/orats_smoke.py SPY`; if FAIL, check network. Restart backend. |
| Backend startup failure (Probe status: DOWN) | ORATS unreachable or token invalid | Edit `app/core/config/orats_secrets.py` if needed. Run smoke test (Section 8). Check network, then restart backend. |
| Port 8000 already in use | Old uvicorn or other process still bound | Section 4: stop Python processes, then `netstat -ano \| findstr :8000` and `taskkill /PID <PID> /F`, or `npx kill-port 8000`. |
| Port 5173 already in use | Old Vite or other process still bound | Section 4: stop Node processes, then kill port 5173 (netstat/taskkill or npx kill-port 5173). |
| Frontend shows "LIVE data unavailable" | Backend not running or not reachable; or CORS/network | Start backend first; confirm http://localhost:8000/api/ops/data-health returns OK. In dev, rely on Vite proxy to avoid CORS. |

---

## 10. DEFINITION OF DONE

You are done when all of the following are true:

- **Stop:** All previous Python and Node processes stopped; ports 8000 and 5173 free.
- **Prerequisites:** Python 3.11+, Node 18+, npm, venv, FastAPI, uvicorn verified (Section 2).
- **ORATS token:** Hardcoded in `app/core/config/orats_secrets.py` (Section 3). No setup required.
- **ORATS smoke:** `python scripts/orats_smoke.py SPY` prints `FINAL VERDICT: PASS` (Section 8).
- **Backend:** Uvicorn started; logs show ORATS BOOT CHECK, Probe status OK, and [ROUTES] registered (Section 5).
- **Backend verification:** `http://localhost:8000/api/ops/data-health` returns `"status": "OK"` (Section 7).
- **Frontend:** `npm run dev` running; http://localhost:5173 loads; in LIVE mode, no "ORATS DOWN", no 404 for /api/* (Section 6–7).
- **Refresh Now:** Button succeeds; no ORATS DOWN banner (Section 7).
- **SPY analysis:** Symbol analysis for SPY works in the UI (Section 7).

If any step fails, use Section 9 (Common Failures & Fixes) and re-run from a clean stop (Section 4).
