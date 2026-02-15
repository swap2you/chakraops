# ChakraOps Execution Runbook

Human runbook for clean-room startup and troubleshooting.

---

## Golden Path (copy-paste)

Run from `chakraops/` for backend; run from `frontend/` for React UI.

```powershell
# Terminal 0: Activate venv, install deps
cd C:\Development\Workspace\ChakraOps\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
pip install -r requirements.txt

# Terminal 1: Generate decision artifacts (LIVE)
cd C:\Development\Workspace\ChakraOps\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out

# Terminal 2: Start backend
cd C:\Development\Workspace\ChakraOps\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.api.server:app --reload --port 8000

# Terminal 3: Start React frontend
cd C:\Development\Workspace\ChakraOps\frontend
npm install
npm run dev

# Terminal 4: Smoke checks (after backend is up)
Invoke-WebRequest -Uri "http://localhost:8000/api/ui/decision/latest?mode=LIVE" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/ui/universe" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/ui/symbol-diagnostics?symbol=SPY" -UseBasicParsing | Select-Object StatusCode
```
Expected: StatusCode 200 for each smoke.

---

## Clean-Room Startup

1. **Kill ports (optional)** – if 8000/5173 are in use:
   ```powershell
   netstat -ano | findstr ":8000"
   netstat -ano | findstr ":5173"
   taskkill /PID <PID> /F
   ```

2. **Clear old artifacts (optional)** – to force fresh decision files:
   ```powershell
   Remove-Item out/decision_*.json -ErrorAction SilentlyContinue
   ```

3. **Generate artifacts** – only `scripts/run_and_save.py` produces decision snapshots.

4. **Start backend** then **frontend** (see Golden Path).

---

## Troubleshooting Matrix

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 8000 or 5173 in use | Another process bound | `netstat -ano \| findstr ":8000"` or `":5173"` → `taskkill /PID <PID> /F` |
| Missing decision files | Artifacts not generated | Run `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out` |
| `ModuleNotFoundError: No module named 'app'` | Wrong PYTHONPATH | From chakraops/: `$env:PYTHONPATH = (Get-Location).Path` |
| No module named uvicorn | Venv not activated | `.\.venv\Scripts\Activate.ps1` before running uvicorn |
| UI shows MOCK in LIVE mode | MOCK data leaking | **STOP**. LIVE must only use `out/`; reject mock/scenario content. |

---

## Data Source Rules (LIVE vs MOCK)

- **LIVE:** Decision artifacts from `scripts/run_and_save.py` → `out/decision_*.json`, `out/decision_latest.json`.
- **MOCK:** Scenario data in `out/mock/` only. Strict separation.
