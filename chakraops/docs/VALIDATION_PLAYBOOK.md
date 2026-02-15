# ChakraOps Validation Playbook

How to verify the system locally before deployment.

## 1. Run Full Test Suite

```bash
cd chakraops
python -m pytest tests/ -v --ignore=tests/e2e -q
```

Expected: All tests pass (some may be skipped if FastAPI or optional deps missing).

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
| Latest run (evaluation store) | `out/evaluations/eval_*.json` |
| Latest pointer | `out/evaluations/latest.json` |
| Run artifacts | `artifacts/runs/YYYY-MM-DD/run_YYYYMMDD_HHMMSSZ/` |
| Latest run JSON | `artifacts/runs/YYYY-MM-DD/run_*/evaluation.json` |
| Latest diagnostics | `artifacts/runs/latest_diagnostics.json` |
| Latest manifest | `artifacts/runs/latest.json` |

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

Open http://localhost:8501, select Run Results from the sidebar.
