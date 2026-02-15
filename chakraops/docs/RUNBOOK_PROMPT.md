# Cursor Validation Prompt

Copy-paste this prompt into Cursor to run a full preflight validation:

---

```
Run a full ChakraOps preflight validation. Execute the following in order:

1. **Version checks**
   - `python --version`
   - `python -m pip --version`
   - Verify venv: `$env:VIRTUAL_ENV` (non-empty)

2. **PYTHONPATH**
   - If cwd is repo root (ChakraOps): `$env:PYTHONPATH = (Join-Path (Get-Location) "chakraops")`
   - If cwd is chakraops/: `$env:PYTHONPATH = (Get-Location).Path`

3. **Compile checks** (from chakraops/)
   - `python -m py_compile run_evaluation.py scripts/run_and_save.py app/ui/live_decision_dashboard.py`

4. **Unit tests**
   - `python -m pytest tests/ -q --ignore=tests/e2e`

5. **Generate decision artifacts (LIVE)**
   - `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out`

6. **Validate output**
   - Confirm `out/decision_latest.json` and at least one `out/decision_*.json` exist.

7. **Provide exact commands for backend and UI** (do not start long-running servers unless requested)
   - Backend: `python -m uvicorn app.api.server:app --reload --port 8000`
   - UI: `python -m streamlit run app/ui/live_decision_dashboard.py --server.port 8501`

8. **Smoke checks** (if servers are running)
   - `Invoke-WebRequest -Uri "http://localhost:8000/api/healthz" -UseBasicParsing`
   - `Invoke-WebRequest -Uri "http://localhost:8000/api/view/universe" -UseBasicParsing`
   - `Invoke-WebRequest -Uri "http://localhost:8000/api/view/symbol-diagnostics?symbol=SPY" -UseBasicParsing`
   - Expected: StatusCode 200 for each.

9. **Summary**
   - List files changed (if any).
   - Commands run + pass/fail.
   - Any failures with file:line fixes.
   - Remaining risks or TODOs.

Constraints:
- Use only `scripts/run_and_save.py` for decision artifacts. No legacy runners.
- Keep LIVE vs MOCK separation. LIVE must not read mock/scenario content.
```
