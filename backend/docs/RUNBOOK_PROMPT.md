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
   - If cwd is chakraops/: `$env:PYTHONPATH = (Get-Location).Path`

3. **Compile checks** (from chakraops/)
   - `python -m py_compile run_evaluation.py scripts/run_and_save.py app/api/server.py app/api/ui_routes.py`

4. **Unit tests**
   - `python -m pytest tests/ -q --ignore=tests/e2e`

5. **Generate decision artifacts (LIVE)**
   - `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out`

6. **Validate output**
   - Confirm `out/decision_latest.json` and at least one `out/decision_*.json` exist.

7. **Frontend build**
   - `cd frontend && npm install && npm run build`

8. **Provide exact commands for backend and frontend**
   - Preferred: `cd C:\Development\Workspace\ChakraOps-dev\chakraops && .\scripts\start_chakraops.ps1`
   - Manual backend: `python -m uvicorn app.api.server:app --reload --host 127.0.0.1 --port 18800`
   - Manual frontend: `cd frontend && npm run dev` (UI at http://127.0.0.1:18873)

9. **Smoke checks** (if backend is running)
   - `Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/decision/latest?mode=LIVE" -UseBasicParsing`
   - `Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/universe" -UseBasicParsing -TimeoutSec 120`
   - `Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/symbol-diagnostics?symbol=SPY" -UseBasicParsing`
   - Expected: StatusCode 200 for each. See RUNBOOK_TROUBLESHOOTING.md if UI fails.

10. **Summary**
    - List files changed (if any).
    - Commands run + pass/fail.
    - Any failures with file:line fixes.
    - Remaining risks or TODOs.

Constraints:
- Use only `scripts/run_and_save.py` for decision artifacts. No legacy runners.
- Keep LIVE vs MOCK separation. LIVE must not read mock/scenario content.
- Frontend calls only /api/ui/* endpoints.
```
