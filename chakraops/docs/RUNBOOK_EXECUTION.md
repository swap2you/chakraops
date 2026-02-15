# ChakraOps Execution Runbook

Human runbook for clean-room startup and troubleshooting.

---

## Golden Path (copy-paste)

Run all commands from `chakraops/` unless noted.

```powershell
# 1. Activate venv, set PYTHONPATH
$env:VIRTUAL_ENV   # verify non-empty
$env:PYTHONPATH = (Get-Location).Path

# 2. Compile checks
python -m py_compile run_evaluation.py scripts/run_and_save.py app/ui/live_decision_dashboard.py

# 3. Unit tests
python -m pytest tests/ -q --ignore=tests/e2e

# 4. Generate decision artifacts (LIVE)
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out

# 5. Validate output
Test-Path out/decision_latest.json
Get-ChildItem out/decision_*.json

# 6. Start backend (Terminal 1)
python -m uvicorn app.api.server:app --reload --port 8000

# 7. Start UI (Terminal 2)
python -m streamlit run app/ui/live_decision_dashboard.py --server.port 8501

# 8. Smoke (separate terminal)
Invoke-WebRequest -Uri "http://localhost:8000/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/view/universe" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/view/symbol-diagnostics?symbol=SPY" -UseBasicParsing | Select-Object StatusCode
```

---

## Clean-Room Startup

1. **Kill ports (optional)** – if 8000/8501 are in use:
   ```powershell
   # Find PIDs
   netstat -ano | findstr ":8000"
   netstat -ano | findstr ":8501"
   # Kill (replace PID)
   taskkill /PID <PID> /F
   ```

2. **Clear old artifacts (optional)** – to force fresh decision files:
   ```powershell
   Remove-Item out/decision_*.json -ErrorAction SilentlyContinue
   ```

3. **Run tests** – see Golden Path step 3.

4. **Generate artifacts** – see Golden Path step 4. Only `scripts/run_and_save.py` produces decision snapshots.

5. **Start services** – backend then UI (Golden Path steps 6–7).

---

## Troubleshooting Matrix

| Issue | Cause | Fix |
|-------|-------|-----|
| Port 8000 or 8501 in use | Another process bound | `netstat -ano \| findstr ":8000"` or `":8501"` → `taskkill /PID <PID> /F` |
| Missing decision files | Artifacts not generated | Run `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out` |
| `ModuleNotFoundError: No module named 'app'` | Wrong PYTHONPATH or cwd | From chakraops/: `$env:PYTHONPATH = (Get-Location).Path`. From repo root: `$env:PYTHONPATH = "...\ChakraOps\chakraops"`. See run_evaluation.py sys.path bootstrap. |
| UI shows MOCK in LIVE mode | MOCK data leaking into LIVE | **STOP**. Fix data source – LIVE must only use `out/` decision files; reject mock/scenario content. |

---

## Data Source Rules (LIVE vs MOCK)

- **LIVE:** Decision artifacts come from `scripts/run_and_save.py` → `out/decision_*.json`, `out/decision_latest.json`.
- **MOCK:** Scenario/mock data must never be used when running LIVE. Strict separation.
