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

#Run full universe evaluation:
python scripts/run_and_save.py --all --output-dir out

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

---

## Canonical Store Path (ONE pipeline / ONE store)

The decision artifact has a **single canonical path** used by scripts, API, and scheduler:

```
<REPO_ROOT>/out/decision_latest.json
```

- **REPO_ROOT** = parent of `chakraops/` (e.g. `C:\Development\Workspace\ChakraOps`).
- **Latest** is written **only** by `EvaluationStoreV2` when `evaluate_universe` or `evaluate_single_symbol_and_merge` runs.
- `scripts/run_and_save.py` writes timestamped copies to `--output-dir` but **never** writes `decision_latest.json` directly; the store does that.
- Server startup logs the resolved path: `[STORE] Canonical decision store path: ...`

---

## Sanity Script

Verifies ONE pipeline / ONE store invariants. Run after the backend is started.

```powershell
cd C:\Development\Workspace\ChakraOps\chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/sanity_one_pipeline.py
```

The script:
1. Runs `run_and_save.py --symbols SPY,AAPL --output-dir out`
2. Reads the canonical store file
3. Calls API: `/api/ui/decision/latest`, `/api/ui/universe`, `/api/ui/symbol-diagnostics?symbol=SPY`
4. Verifies: `artifact_version == v2`, store vs API `pipeline_timestamp` match, universe/symbol-diagnostics score/band consistency

**Exit codes:**
- `0` – PASS
- `2` – SANITY FAIL

### SANITY FAIL: What it means and how to diagnose

| Message | Cause | How to diagnose |
|---------|-------|------------------|
| `run_and_save failed` | Evaluation or store write failed | Check stderr of run_and_save; ORATS/env issues |
| `Store file not found` | No artifact at canonical path | Run `run_and_save.py` first; check `[STORE] Canonical decision store path` at server startup |
| `decision/latest not v2` | API returned non-v2 or 404 | Ensure backend uses EvaluationStoreV2; restart server and re-run evaluation |
| `decision/latest metadata.pipeline_timestamp != store` | API serving stale or different artifact | Restart server so it loads the store; or API read from wrong path |
| `Universe SPY score/band == decision symbols SPY` fail | Universe and decision response disagree | Single store should be source; check ui_routes universe vs decision path |
| `symbol-diagnostics SPY vs store SPY` fail | Symbol-diagnostics not store-first | Check `_build_symbol_diagnostics_from_v2_store` uses store only |
| `API: Connection refused` / `Cannot reach API` | Server not running | Start backend on port 8000 before running sanity |
