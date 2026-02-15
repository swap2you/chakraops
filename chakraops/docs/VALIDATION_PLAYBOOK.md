# ChakraOps Validation Playbook

How to verify the system locally before deployment.

---

## Preflight + Startup (Windows, PowerShell)

### 1. Verify versions
```powershell
python --version
python -m pip --version
```

### 2. Verify venv is active
```powershell
$env:VIRTUAL_ENV
```
If empty, activate your venv first.

### 3. Set PYTHONPATH

**If running from repo root (e.g. …/ChakraOps):**
```powershell
cd ChakraOps
$env:PYTHONPATH = (Join-Path (Get-Location) "chakraops")
```

**If running from chakraops/ (e.g. …/ChakraOps/chakraops):**
```powershell
cd chakraops
$env:PYTHONPATH = (Get-Location).Path
```

### 4. Compile checks
```powershell
python -m py_compile run_evaluation.py scripts/run_and_save.py app/ui/live_decision_dashboard.py
```
*Run from chakraops/ so paths resolve.*

### 5. Unit tests
```powershell
python -m pytest tests/ -q --ignore=tests/e2e
```

### 6. Generate decision artifacts (LIVE)
```powershell
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out
```

### 7. Validate output files
```powershell
Test-Path out/decision_latest.json
Get-ChildItem out/decision_*.json
```

### 8. Start backend (Terminal 1)
```powershell
python -m uvicorn app.api.server:app --reload --port 8000
```

### 9. Start UI (Terminal 2)
```powershell
python -m streamlit run app/ui/live_decision_dashboard.py --server.port 8501
```

### 10. Quick API smoke (separate terminal)
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/view/universe" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://localhost:8000/api/view/symbol-diagnostics?symbol=SPY" -UseBasicParsing | Select-Object StatusCode
```
Expected: StatusCode 200 for each.

---

## 1. Run Full Test Suite

```bash
cd chakraops
python -m pytest tests/ -v --ignore=tests/e2e -q
```

**Windows PowerShell:**
```powershell
cd chakraops
$env:PYTHONPATH=(Get-Location).Path
python -m pytest tests/ -q --ignore=tests/e2e
```

**⚠️ WARNING:** Do not paste individual pytest assert lines into PowerShell. Always run the full `python -m pytest ...` command. Pasting assert output will cause errors.

## 2. Run Nightly Evaluation Manually

```bash
cd chakraops
python -m chakraops.run_evaluation --mode nightly --asof last_close
```

Or dry-run (no Slack, no external calls):

```bash
python -m chakraops.run_evaluation --mode nightly --dry-run
```

### Overrides

- `--use-universe`: Use symbols from config/universe.csv (default).
- `--symbols AAPL,SPY,NVDA`: Override with specific symbols.
- `NIGHTLY_MAX_SYMBOLS=5`: Limit symbols via env.

## 3. Output Locations

| Artifact | Path |
|----------|------|
| Decision snapshots (Live Decision Monitor) | `out/decision_<timestamp>.json`, `out/decision_latest.json` |
| Latest run (evaluation store) | `out/evaluations/eval_*.json` |
| Latest pointer | `out/evaluations/latest.json` |
| Run artifacts | `artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/` |
| Latest run JSON | `artifacts/runs/YYYY-MM-DD/run_*/evaluation.json` |
| Latest diagnostics | `artifacts/runs/latest_diagnostics.json` |
| Latest manifest | `artifacts/runs/latest.json` |

**Decision snapshots** are produced only by `scripts/run_and_save.py`.

## 4. UI Smoke Checks

1. **Run Results tab**
   - Navigate to Run Results.
   - Summary cards show status, evaluated, skipped, duration.
   - Table shows Symbol, Status, Score, Band, Mode, Strike, DTE, Premium.
   - Filters work: Tier, Band, Verdict/Status, Cluster risk.
   - Symbol drilldown: select symbol → Stage-1, Stage-2, Sizing, Exit Plan, Traces, Raw JSON in that order.
   - Export: Download latest run JSON, Download diagnostics JSON.

2. **Symbol drilldown**
   - Stage-1: Data sufficiency, data_as_of, endpoints_used.
   - Stage-2: Score, Band, eligibility status, fail_reasons.
   - Sizing: baseline_contracts, guardrail_adjusted_contracts, advisories.
   - Exit plan: T1, T2, dte_targets, priority.

3. **Diagnostics tab**
   - Recent Runs table: run_id, as_of, status, duration, evaluated, eligible, warnings.
   - Wall time, requests_estimated, cache hit rate by endpoint.
   - Watchdog warnings list.
   - Budget: requests_estimated, max_requests_estimate, budget_stopped.

4. **Portfolio Command Center**
   - Loads without error (if used by your UI).

## 5. Slack Smoke Checks

- **DAILY summary**: Includes Portfolio Risk Summary section when enabled.
- **Universe Gates line**: Appears only in DAILY when Phase 9.0 gates are enabled and skips exist.

## 6. API Endpoints (Quick Verify)

```bash
# Health
curl http://localhost:8000/api/healthz

# Latest run
curl http://localhost:8000/api/eval/latest-run

# Runs list
curl "http://localhost:8000/api/eval/runs?limit=10"

# Symbol drilldown
curl http://localhost:8000/api/eval/symbol/AAPL

# System health
curl http://localhost:8000/api/system/health

# Exports (download)
curl -o latest_run.json http://localhost:8000/api/eval/export/latest-run
curl -o diagnostics.json http://localhost:8000/api/eval/export/diagnostics
```

## 7. Start Backend + UI

```bash
# Terminal 1: API
uvicorn app.api.server:app --reload --port 8000

# Terminal 2: Streamlit
streamlit run app/ui/live_decision_dashboard.py --server.port 8501
```

**Windows PowerShell:**
```powershell
cd chakraops
$env:PYTHONPATH=(Get-Location).Path

# Terminal 1: API
python -m uvicorn app.api.server:app --reload --port 8000

# Terminal 2: Streamlit
python -m streamlit run app/ui/live_decision_dashboard.py --server.port 8501
```

Open http://localhost:8501. Generate decision artifacts first (see Fresh Start below) so the dashboard has data.

---

## 8. Kill Running Processes (Windows)

If uvicorn or Streamlit is stuck, stop them:

- **In terminal**: Press `Ctrl+C` to stop the running process.
- **Kill by port**:
  ```powershell
  netstat -ano | findstr :8000
  netstat -ano | findstr :8501
  taskkill /PID <PID> /F
  ```
  Replace `<PID>` with the Process ID from the second column.

---

## 9. Fresh Start

### LIVE mode (default)

The Live Decision Monitor reads `out/decision_*.json` in LIVE mode. **One script produces these**: `scripts/run_and_save.py`.

1. **Activate venv and set PYTHONPATH**:
   ```powershell
   cd chakraops
   $env:PYTHONPATH=(Get-Location).Path
   ```

2. **Run the decision snapshot generator** (produces a BLOCKED/HOLD artifact even on weekends):
   ```powershell
   python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out
   ```
   Writes `out/decision_<timestamp>.json` and `out/decision_latest.json`.

3. **Start the API** (Terminal 1):
   ```powershell
   python -m uvicorn app.api.server:app --reload --port 8000
   ```

4. **Start Streamlit** (Terminal 2):
   ```powershell
   python -m streamlit run app/ui/live_decision_dashboard.py --server.port 8501
   ```

5. Open http://localhost:8501. Ensure mode is **LIVE** and select the latest decision file.

### MOCK mode (scenario testing)

Place scenario JSON files (e.g. `scenario_*.json`) in `out/mock/`. Create the folder if missing:
```powershell
mkdir -Force out\mock
```
Set the sidebar mode to **MOCK**. The UI will list and load files from `out/mock/` only.
