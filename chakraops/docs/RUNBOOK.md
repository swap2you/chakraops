# ChakraOps Operator Runbook

Single entry point for daily operation, smoke tests, debugging, and validation. Use this runbook to run, verify, and troubleshoot the system.

---

## 1. Quick Start

### Prerequisites

- **Python 3.11+:** `python --version`
- **Node 18+:** `node --version`
- **Backend deps (from `chakraops`):** `pip install -r requirements.txt` (includes FastAPI, uvicorn)
- **ORATS token:** Configure via `.env` or project config (see [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md)). Never commit secrets.

### Start backend

```bash
cd chakraops
# Optional: activate venv first, e.g. .\.venv\Scripts\Activate.ps1
uvicorn app.api.server:app --reload --port 8000
```

Or:

```bash
cd chakraops
python scripts/run_api.py
```

### Start frontend (after backend is up)

```bash
cd frontend
npm install
npm run dev
```

- Backend: http://localhost:8000  
- Frontend: http://localhost:5173 (Vite proxies `/api` to backend when `VITE_API_BASE_URL` unset in dev)

### Verify stack

- Backend health: `GET http://localhost:8000/health` → 200, `{"ok": true, "status": "healthy"}`
- Data health: `GET http://localhost:8000/api/ops/data-health` → returns sticky status (see **ORATS data health semantics** below)
- Frontend: Open app, switch to LIVE, click **Refresh now** — no 404, no "ORATS DOWN" if backend is healthy

**ORATS data health semantics (Phase 8B):** Status is **sticky** and persisted to `out/data_health_state.json`.  
- **UNKNOWN** — No successful ORATS call has ever occurred (e.g. first start, or after reset).  
- **OK** — Last successful call within evaluation window (default 30 min; `EVALUATION_QUOTE_WINDOW_MINUTES`).  
- **WARN** — Last success is beyond the window (stale); data may still be usable for evaluation.  
- **DOWN** — Last attempt failed and no recent success (or never succeeded).  
The UI does not flicker UNKNOWN→OK because status is derived from persisted `last_success_at`; a live probe runs only when status is UNKNOWN.

---

## 2. Daily Workflow

### Start of day

1. **Health:** Open app; confirm no "Evaluation run in progress" stuck. If stuck, restart backend (stale lock clears on startup).
2. **Latest run:** Dashboard shows last COMPLETED run. If "No completed run" and market is open, wait for next scheduled run or trigger once manually.
3. **Alerts:** Check Notifications page for overnight SYSTEM or DATA_HEALTH alerts. Act on CRITICAL; WARN/INFO as needed.

### Intraday

1. **Dashboard:** Eligible/shortlist from last COMPLETED run. "Run in progress" banner = wait; do not re-trigger.
2. **Universe:** Symbol list from `config/universe.csv`. Changes require backend reload or next run.
3. **History:** "View run" to compare; "Back to latest" to return.
4. **Alerts:** Slack (if configured) and Notifications. SIGNAL = informational. REGIME_CHANGE = review strategy. DATA_HEALTH/SYSTEM = investigate.

### End of day

1. Ensure at least one COMPLETED run (History page).
2. Scan SYSTEM/FAILED or repeated DATA_HEALTH; fix before next day if needed.

### How the system runs

- **Scheduler:** Evaluation every **N** minutes (default 15; `UNIVERSE_EVAL_MINUTES`, range 1–120). Runs only when market is OPEN. See [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md).
- **Runs:** One at a time (file lock). States: RUNNING → COMPLETED or FAILED. Dashboards show last COMPLETED.
- **Manual trigger:** "Run evaluation now" in UI or `POST /api/ops/evaluate-now`. Skipped if a run is in progress.

### UI at a glance

| Page | What it shows |
|------|----------------|
| **Dashboard** | Last COMPLETED run: eligible count, shortlist, top symbols. Banner when RUNNING. |
| **Universe** | Symbols from config + evaluation summary. |
| **History** | All runs; "View run" opens Dashboard for that run. |
| **Notifications** | Alerts (type, severity, sent/suppressed). See [ALERTING.md](./ALERTING.md). |
| **Pipeline** | Stage reference and reason codes. See [ARCHITECTURE.md](./ARCHITECTURE.md). |
| **Diagnostics / Ticker** | Per-symbol data completeness, gates, verdict. Use when a symbol is BLOCKED or missing. |

### Alerts: action vs ignore

| Alert type | Severity | Action |
|------------|----------|--------|
| **SYSTEM** | CRITICAL | Check logs; fix data/ORATS/network; re-run. |
| **DATA_HEALTH** | WARN/CRITICAL | Check symbol diagnostics and data sources. |
| **REGIME_CHANGE** | WARN | Review strategy for new regime. |
| **SIGNAL** | INFO | Optional: review Dashboard/History. |

Slack does not execute trades. Alerts are notifications only.

### Why the system may BLOCK

- **Required data missing:** Price, IV rank, bid, ask, volume, or candidate delta missing → BLOCKED. No inference. See [DATA_CONTRACT.md](./DATA_CONTRACT.md).
- **Portfolio/risk limits:** Would exceed capital, sector, or position limits. See [PHASE3_PORTFOLIO_AND_RISK.md](./PHASE3_PORTFOLIO_AND_RISK.md).
- **Market regime:** e.g. RISK_OFF. Stale data (> 1 trading day) → WARN unless contract says BLOCK.

### BLOCKED vs UNKNOWN vs WARN

| Term | Meaning |
|------|---------|
| **BLOCKED** | System refuses to recommend. A reason is always provided. Fix the cause; do not override without accepting risk. |
| **UNKNOWN** | Not enough information (e.g. return on risk when risk amount not set at entry). Treat as non-actionable; do not infer. |
| **WARN** | Proceed with caution; optional data missing or stale. Review before acting. |

---

## 3. Smoke Tests

Use before release or after deploy. No automation required; follow manually.

### When to run

- Before tagging a release or baseline.
- After deploying backend or frontend.
- After changes that affect boot, health, or evaluation.

### Backend smoke

**Without ORATS token**

1. Start backend: `cd chakraops && python scripts/run_api.py`
2. `GET /health` → 200. `GET /api/healthz` → 200.
3. Trigger evaluation (e.g. POST `/api/ops/evaluate-now` with API key if set). System must not crash; evaluation completes or gracefully BLOCKS with data reasons (e.g. required_data_missing).

**With ORATS token**

1. Set valid ORATS token (e.g. in `.env`).
2. Start backend; run one evaluation.
3. Confirm `required_data_missing` / `required_data_stale` and `data_sufficiency` (PASS/WARN/FAIL) per [DATA_CONTRACT.md](./DATA_CONTRACT.md).

### Frontend smoke

1. **Build:** `cd frontend && npm run build` — must succeed (chunk size warning OK).
2. Load app; open: Dashboard, Ranked Universe, one Ticker page, Tracked Positions, Decision Quality.
3. BLOCKED: UI shows BLOCKED and reasons. UNKNOWN: shown for missing decision-critical fields (no blank/NA).

### Failed smoke

- Backend does not start or health non-2xx.
- Unhandled exception when triggering evaluation.
- Frontend build fails or any listed page fails to load.
- BLOCKED not shown with reasons; UNKNOWN replaced by blank/NA.

### ORATS smoke (before relying on LIVE data)

```bash
cd chakraops
python scripts/orats_smoke.py SPY
```

Expect: HTTP 200, row count, `FINAL VERDICT: PASS`. If FAIL: check token, network, rate limit. Do not start frontend for LIVE until this passes.

---

## 4. Debugging Playbook

### Common failure modes

| Symptom | Likely cause | Resolution |
|---------|--------------|------------|
| "No completed run" for long | No COMPLETED run yet; or latest pointer missing/corrupt | Wait or trigger once. Check History for FAILED; check `out/evaluations/latest.json`. |
| "Evaluation run in progress" never clears | Backend crashed; stale lock | Restart backend. See [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md). |
| All symbols BLOCKED or low eligible | Regime RISK_OFF, data issues, strict gates | Check regime; run symbol diagnostics; confirm ORATS and universe. |
| 401 on API calls | Wrong or missing `X-API-Key` | Use same key as backend `CHAKRAOPS_API_KEY`. Frontend: `VITE_API_KEY`. |
| Slack alerts not received | Webhook unset/wrong or suppressed | Set webhook; check Notifications for "suppressed". See [ALERTING.md](./ALERTING.md). |
| Run fails repeatedly (FAILED) | ORATS timeout, network, bad symbol/data | Check logs; run ORATS smoke; reduce universe or fix data. |
| 404 on /api/* | Backend not running or wrong base URL | Ensure backend on 8000. Dev: use Vite proxy (no `VITE_API_BASE_URL` for same-origin). |
| ORATS DOWN banner | Backend probe failed or data-health not OK | Check token/config; run `python scripts/orats_smoke.py SPY`; restart backend. |
| Port 8000 or 5173 in use | Old process still bound | Stop Python/Node; e.g. `netstat -ano | findstr :8000` then `taskkill /PID <PID> /F`, or `npx kill-port 8000`. |

### LIVE mode verification

1. Set `VITE_API_BASE_URL` to API (e.g. `http://localhost:8000`) if frontend and API on different origins.
2. Refresh now → no 404; success or clear "Refresh failed: …" with URL.
3. Analytics → Universe loads or shows "Universe unavailable (API error)" with retry.
4. Analysis → enter SPY (or symbol); result shown (eligible or OUT_OF_SCOPE); no "Analysis failed" for 200.

### Backend routes (reference)

- `GET /health`, `GET /api/healthz` — no auth
- `GET /api/ops/data-health`, `GET /api/ops/routes` — API discovery
- `GET /api/view/universe`, `GET /api/view/symbol-diagnostics?symbol=SYMBOL`
- `POST /api/ops/evaluate` — trigger run (API key if `CHAKRAOPS_API_KEY` set)

---

## 5. Validation Commands

### Backend tests (no ORATS token required)

```bash
cd chakraops
python -m pytest tests/ -v --tb=short
```

Subsets:

```bash
python -m pytest tests/test_phase6_data_dependencies.py tests/test_ranking.py -v
python -m pytest tests/test_evaluation_integration.py -v
python -m pytest tests/test_data_completeness_report.py -v
```

### Frontend

```bash
cd frontend
npm run build
npm run test -- --run
```

### Lint (optional)

```bash
cd chakraops
pip install ruff
ruff check app tests
```

### Deployment validation checklist

- Backend: `GET /health` → 200. `GET /api/view/evaluation/latest` with `X-API-Key` → 200 or "no runs".
- Frontend: App loads; API calls use `VITE_API_BASE_URL` + `VITE_API_KEY` when set.
- Scheduler: Within one interval, a run appears in History or logs show "market closed" / "already in progress".
- Alerts: If Slack configured, trigger a run and confirm alert in channel or Notifications.

---

## 6. What Not To Do

- **Do not** commit `.env` or any file with secrets. See [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md).
- **Do not** re-trigger evaluation while "Run in progress" is shown; wait or restart backend if stuck.
- **Do not** treat UNKNOWN as a number; do not infer when data is missing.
- **Do not** override BLOCKED with manual execution unless you explicitly accept the risk.
- **Do not** assume broker integration or automated trading; execution is manual by the operator.
- **Do not** bypass GitHub or tooling push protection for secrets.

---

## 7. Operator Playbook: What To Do When Something Looks Wrong

Use this section when something looks wrong: a symbol is BLOCKED, risk shows UNKNOWN, there are no opportunities, or the UI doesn’t match the backend.

### Prerequisites checklist

Before debugging, confirm:

- **Python 3.11+:** `python --version`
- **Node 18+:** `node --version` (for frontend)
- **Env vars:** `.env` in `chakraops/` if using ORATS (see [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md)). `CHAKRAOPS_API_KEY` and `VITE_API_KEY` only if you use API-key–protected endpoints.
- **ORATS:** Optional. Without a token, evaluation still runs but will BLOCK with data reasons (e.g. `required_data_missing`). With a token, run `python scripts/orats_smoke.py SPY` to verify.

### Startup sequence

1. **Backend first:** From `chakraops/`: `uvicorn app.api.server:app --reload --port 8000` or `python scripts/run_api.py`.
2. **Then frontend:** From `frontend/`: `npm run dev`. Frontend proxies `/api` to backend when `VITE_API_BASE_URL` is unset.
3. **Then evaluation:** Trigger via UI “Run evaluation now” or `POST /api/ops/evaluate-now`. Do not trigger again while “Run in progress” is shown.

### Daily workflow (what normally runs, what files are produced)

- **Scheduler:** When market is OPEN, evaluation runs every N minutes (config: `UNIVERSE_EVAL_MINUTES`, default 15). One run at a time (file lock).
- **Produced files:** `out/evaluations/{run_id}.json` (full run), `out/evaluations/latest.json` (pointer to latest completed). `out/market/market_regime.json` (regime). `out/audit/`, `out/alerts/`, `out/notifications/` for logs.

### Smoke tests (exact commands)

```bash
# Backend health (no ORATS required)
curl -s http://localhost:8000/health
curl -s http://localhost:8000/api/healthz

# Backend tests
cd chakraops && python -m pytest tests/ -v --tb=short

# Frontend build
cd frontend && npm run build

# ORATS smoke (only when using ORATS)
cd chakraops && python scripts/orats_smoke.py SPY
```

### Debug decision tree

**Symbol BLOCKED → where to look**

1. **API:** `GET /api/view/symbol-diagnostics?symbol=SYMBOL` — `verdict_reason_code`, `primary_reason`, `missing_fields`, `required_data_missing`, `data_completeness`.
2. **Data sufficiency:** `GET /api/symbols/{symbol}/data-sufficiency` (or equivalent) — `status` (PASS/WARN/FAIL), `required_data_missing`, `required_data_stale`. See [DATA_CONTRACT.md](./DATA_CONTRACT.md).
3. **Run JSON:** `out/evaluations/latest.json` → `symbols[]` for that symbol: `stage_reached`, `liquidity_reason`, `position_reason`, `verdict_reason_code`.
4. **Regime:** `out/market/market_regime.json` — RISK_OFF blocks new CSP. Run-level `regime` in evaluation JSON.

**UNKNOWN risk → where to look**

- UNKNOWN (e.g. return on risk) means data not set (e.g. `risk_amount_at_entry` at position entry). Check position/tracked-position APIs and journal; do not infer a number. See [DATA_CONTRACT.md](./DATA_CONTRACT.md) (risk inputs).

**No opportunities → where to look**

1. **Regime:** RISK_OFF → no new CSP; scores capped. Check `out/market/market_regime.json` and run-level `regime`.
2. **Universe:** `config/universe.csv` and `GET /api/view/universe` — correct symbols and no empty list.
3. **Data:** Many symbols BLOCKED for `required_data_missing` or `DATA_INCOMPLETE_FATAL` → check ORATS token, network, and data-health: `GET /api/ops/data-health`.
4. **History:** Last run COMPLETED? If FAILED, check logs and `out/evaluations/` for the failed run_id.

**UI mismatch vs backend → how to confirm**

1. **Backend truth:** `GET /api/view/evaluation/latest` (or `GET /api/view/evaluation/{run_id}`) — counts and `symbols[]`. Compare with what the UI shows.
2. **Frontend base URL:** If UI calls wrong host, set `VITE_API_BASE_URL` to backend (e.g. `http://localhost:8000`) and rebuild/restart.
3. **Caching:** Hard refresh or clear cache; ensure UI is not showing an old run (e.g. “View run” vs “Back to latest”).

### Key files to inspect

| Location | Purpose |
|----------|---------|
| `out/evaluations/latest.json` | Pointer to latest completed run. |
| `out/evaluations/{run_id}.json` | Full run: regime, counts, per-symbol verdicts, reasons, scores. |
| `out/market/market_regime.json` | Current regime (RISK_ON/NEUTRAL/RISK_OFF). |
| `out/audit/*.jsonl` | Audit log (if enabled). |
| `out/alerts/*.jsonl` | Alert log. |
| Data-sufficiency API | Per-symbol PASS/WARN/FAIL and missing/stale lists. |

### What NOT to do (playbook)

- Do **not** assume broker automation or auto-execution; execution is manual.
- Do **not** override BLOCKED by inferring missing data or forcing a trade; fix the cause or accept risk explicitly.
- Do **not** treat UNKNOWN as a numeric value; do not infer.
- Do **not** re-trigger evaluation while a run is in progress; wait or restart backend if stuck.

---

## 8. Further Reading

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | How the system works: pipeline, scoring, bands, strategy. |
| [DATA_CONTRACT.md](./DATA_CONTRACT.md) | Required/optional data, staleness, BLOCKED/WARN/PASS, override rules. |
| [BASELINE.md](./BASELINE.md) | Baseline definition, release discipline, breaking changes. |
| [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md) | Scheduler, nightly, lock, run lifecycle. |
| [ALERTING.md](./ALERTING.md) | Slack policy, channel mapping. |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | Railway + Vercel, env vars, access gate. |
| [REGRESSION_CONTRACT.md](./REGRESSION_CONTRACT.md) | Nightly tests and guarantees. |
| [SECRETS_AND_ENV.md](./SECRETS_AND_ENV.md) | Secrets policy, .env, tests. |
| [PHASE3_PORTFOLIO_AND_RISK.md](./PHASE3_PORTFOLIO_AND_RISK.md) | Portfolio and risk limits. |

---

## 9. Housekeeping

### Archiving `out/` (evaluation artifacts)

To avoid unbounded growth of `out/evaluations/` and related artifacts:

- **Keep recent hot:** Last 14 or 30 days of evaluation JSONs remain in `out/evaluations/`.
- **Archive older:** Older run files are moved (or zipped) into `out/archive/` by a dedicated script.

**Procedure:**

1. Run the archiving script from the `chakraops` directory (see [tools/archive_out.py](../tools/archive_out.py)):
   ```bash
   cd chakraops
   python tools/archive_out.py --keep-days 30
   ```
2. Script copies or moves evaluation files older than `--keep-days` into `out/archive/` (optionally in a date-based subfolder or zip). Recent files and `latest.json` are left in place.
3. Run periodically (e.g. weekly via cron or manually). Default `--keep-days` is 30 if not specified.

Details and options are in the script docstring. This is non-destructive: archived files are moved, not deleted.
