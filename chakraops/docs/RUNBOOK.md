# Operator Runbook (Phase 8)

Single runbook for daily use, validation, and troubleshooting. Concise; links to detailed docs where needed.

---

## How the system runs

- **Scheduler:** Evaluation runs automatically every **N** minutes (default 15; set `UNIVERSE_EVAL_MINUTES`, range 1–120). Runs only when market is **OPEN**. See [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md).
- **Runs:** One evaluation at a time (file lock). States: **RUNNING** → **COMPLETED** or **FAILED**. Dashboards show the **last COMPLETED** run by default.
- **Nightly:** Optional run at a fixed time (e.g. 19:00 ET). Config: `NIGHTLY_EVAL_TIME`, `NIGHTLY_EVAL_TZ`, `NIGHTLY_EVAL_ENABLED`.
- **Manual trigger:** "Run evaluation now" in the UI (or POST `/api/ops/evaluate-now`). Skipped if a run is already in progress.

---

## Daily operator workflow

### Start of day

1. **Health:** Open app; confirm no "Evaluation run in progress" stuck (if stuck, backend may have crashed — restart backend; lock clears on startup if stale).
2. **Latest run:** Dashboard shows last COMPLETED run. If "No completed run" and market is open, wait for next scheduled run or trigger once manually.
3. **Alerts:** Check Notifications page for overnight SYSTEM or DATA_HEALTH alerts. Act on CRITICAL (e.g. run failed); WARN/INFO as needed. See [Alerts: action vs ignore](#alerts-action-vs-ignore) below.

### Intraday

1. **Dashboard:** Shows eligible/shortlist counts and symbols from last COMPLETED run. "Run in progress" banner = wait; do not re-trigger.
2. **Universe:** Confirm symbol list matches intent (`config/universe.csv`). Changes require backend reload or next run.
3. **History:** Use "View run" to compare a prior run to current; "Back to latest" to return.
4. **Alerts:** Slack (if configured) and Notifications page. SIGNAL = set changed (informational). REGIME_CHANGE = review strategy. DATA_HEALTH/SYSTEM = investigate.

### End of day

1. **Last run:** Ensure at least one COMPLETED run for the day (History page).
2. **Alerts:** Scan for SYSTEM/FAILED or repeated DATA_HEALTH; fix before next day if needed.
3. **No action required** for normal SIGNAL/REGIME_CHANGE unless you change strategy.

---

## How to interpret the UI

| Page | What it shows | Operator takeaway |
|------|----------------|-------------------|
| **Dashboard** | Last COMPLETED run: eligible count, shortlist, top symbols, run id. Banner when a run is RUNNING. | Truth = last completed run. If banner says "in progress", wait. Use "Viewing prior run" + "Back to latest" when comparing runs. |
| **Universe** | Symbols loaded from config + evaluation summary (evaluated/eligible/shortlist). | Matches `config/universe.csv`. Counts come from latest completed run. |
| **History** | All runs (RUNNING, COMPLETED, FAILED) with status, time, duration, counts. | "View run" opens Dashboard for that run. Use to audit or compare. |
| **Notifications** | Evaluation alerts + Phase 6 system alerts (alert type, severity, summary, sent/suppressed). | See [Alerts: action vs ignore](#alerts-action-vs-ignore). |
| **Pipeline** | Stage-by-stage reference (same as [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md)). | Use for reason codes and "where to verify" when debugging a symbol or run. |
| **Diagnostics / Ticker** | Per-symbol diagnostics (data completeness, gates, verdict). | Use when a symbol is BLOCKED or missing; confirms data source and stage. |

Details on pipeline stages, reason codes, and data sources: [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md).

---

## Alerts: action vs ignore

| Alert type | Severity | Action | Ignore when |
|------------|----------|--------|-------------|
| **SYSTEM** | CRITICAL | Check logs; fix data/ORATS/network; re-run evaluation. | — |
| **DATA_HEALTH** | WARN/CRITICAL | Check symbol diagnostics and data sources; fix missing/errors. | Single transient error already resolved. |
| **REGIME_CHANGE** | WARN | Review strategy suitability for new regime (e.g. RISK_OFF → more defensive). | You already adjusted. |
| **SIGNAL** | INFO | Optional: review Dashboard/History for new eligible/shortlist. | No trade decision needed. |

**What Slack does *not* do:** No trade execution. Alerts are notifications only. See [ALERTING.md](./ALERTING.md) for Slack policy and channel mapping.

---

## Deployment validation checklist

Use after deploying (e.g. Railway + Vercel). See [DEPLOYMENT.md](./DEPLOYMENT.md) for full steps.

- [ ] **Backend:** `GET /health` returns 200 (no API key). `GET /api/view/evaluation/latest` with `X-API-Key` returns 200 (or "no runs").
- [ ] **Frontend:** Access gate (if `VITE_APP_PASSWORD` set) and app load; API calls use `VITE_API_BASE_URL` + `VITE_API_KEY`.
- [ ] **Scheduler:** Within one interval after deploy, either a run appears in History or logs show "market closed" / "already in progress".
- [ ] **Alerts:** If Slack is configured, trigger a run and confirm one alert type (e.g. SIGNAL) appears in the expected channel or in Notifications page.

---

## Common failure modes and resolutions

| Symptom | Likely cause | Resolution |
|---------|--------------|------------|
| Dashboard shows "No completed run" for long | No COMPLETED run yet; or latest pointer missing/corrupt | Wait for next run or trigger once. Check History for FAILED runs; check `out/evaluations/latest.json` and run files. |
| "Evaluation run in progress" never clears | Backend crashed during run; stale lock | Restart backend (stale lock cleared on startup after 2h or on startup). See [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md). |
| All symbols BLOCKED or low eligible | Regime RISK_OFF, data issues, or strict gates | Check regime in run/API; run symbol diagnostics; confirm ORATS and universe config. See [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md). |
| 401 on API calls | Wrong or missing `X-API-Key` | Use same key as backend `CHAKRAOPS_API_KEY`. Frontend: `VITE_API_KEY`. See [DEPLOYMENT.md](./DEPLOYMENT.md). |
| Slack alerts not received | `SLACK_WEBHOOK_URL` unset or wrong; or alerts suppressed (cooldown/disabled type) | Set webhook in env; check Notifications page for "suppressed" reason. See [ALERTING.md](./ALERTING.md). |
| Run fails repeatedly (FAILED) | ORATS timeout, network, or bad symbol/data | Check logs for exception; run ORATS smoke test; reduce universe or fix data. See [RUNBOOK_EXECUTION.md](./RUNBOOK_EXECUTION.md) for local run and ORATS. |

---

## Why the system may refuse to trade (Phase 6)

The system will **BLOCK** an opportunity (refuse to recommend) when:

1. **Required data missing:** Price, IV rank, bid, ask, volume, or candidate delta not provided by the data source. See [data_dependencies.md](./data_dependencies.md). No inference is made; missing = BLOCKED.
2. **Portfolio/risk limits:** Would exceed max capital utilization, sector limits, or position limits. See [PHASE3_PORTFOLIO_AND_RISK.md](./PHASE3_PORTFOLIO_AND_RISK.md).
3. **Market regime:** RISK_OFF or other regime gate. See pipeline docs.

**Stale data** (e.g. ORATS quote > 1 trading day old) produces **WARN**, not BLOCK, unless data_dependencies.md specifies BLOCK for that field.

---

## How to interpret BLOCKED vs UNKNOWN

| Term | Meaning | What to do |
|------|---------|------------|
| **BLOCKED** | The system explicitly refuses to recommend. A reason is always provided (e.g. "Required data missing: bid, iv_rank" or "Sector limit exceeded"). | Fix the cause (data source, limits, or regime). Do not override with manual execution unless you accept the risk. |
| **UNKNOWN** | The system does not have enough information to compute a value (e.g. return on risk when risk amount was not set at entry). | Treat as non-actionable for that metric. Do not infer a number. |
| **WARN** | Proceed with caution; optional data missing or data stale, or nearing a limit. | Review before acting; you may still execute manually with full awareness. |

Details: [data_sufficiency.md](./data_sufficiency.md), [decision_quality.md](./decision_quality.md).

---

## Quick links

- **Scheduling and run lifecycle:** [SCHEDULING_AND_RUNS.md](./SCHEDULING_AND_RUNS.md)
- **Pipeline stages and reason codes:** [EVALUATION_PIPELINE.md](./EVALUATION_PIPELINE.md)
- **Alerts and Slack policy:** [ALERTING.md](./ALERTING.md)
- **Deployment (Railway + Vercel):** [DEPLOYMENT.md](./DEPLOYMENT.md)
- **Local run (backend + frontend, ORATS):** [RUNBOOK_EXECUTION.md](./RUNBOOK_EXECUTION.md)
