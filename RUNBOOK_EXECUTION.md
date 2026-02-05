# ChakraOps Frontend — Execution Runbook

Runbook for running, testing, and demoing the ChakraOps React frontend (Phase 7.1–8.6). Read-only UI; no execution, journaling, or strategy configuration.

---

## Prerequisites

- **Node.js** — Recommend **Node 20 LTS**. Use the version in `frontend/.nvmrc` (e.g. 20.11.1).
- **npm** — Ships with Node.
- **nvm-windows** (optional): [nvm-windows](https://github.com/coreybutler/nvm-windows) for switching Node versions.

```powershell
nvm install 20
nvm use 20
```

Node 22 is unsupported for now due to optional dependency resolution; use Node 20 LTS for a stable build.

---

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Default route is `/dashboard`.

### Rollup on Windows

Scripts set `ROLLUP_SKIP_NODEJS_NATIVE=1` so Rollup uses its JavaScript fallback. If you see native binary errors, ensure you run `npm run dev` / `npm run build` as above.

---

## Tests

```powershell
cd frontend
npm run test
```

Runs Vitest once. Use `npm run test:watch` for watch mode.

---

## Build

```powershell
cd frontend
npm run build
```

Requires `@types/node` and `tsconfig.node.json` with `"types": ["node"]` so `node:path` / `node:url` in `vite.config.ts` resolve. Output is in `frontend/dist`.

---

## Typecheck (no emit)

```powershell
cd frontend
npm run typecheck
```

Runs `tsc --noEmit` to validate types without building.

---

## Check (test + build)

```powershell
cd frontend
npm run check
```

Runs `npm run test` then `npm run build` in sequence. Use before commit or push.

---

## Troubleshooting

### Common Windows issues

- **Path / node:path errors** — Ensure Node 20 LTS and `@types/node` installed. `tsconfig.node.json` should include `"types": ["node"]`.
- **nvm** — If using nvm-windows, run `nvm use 20` from a fresh shell if Node version is wrong.
- **Optional deps** — If `@rollup/rollup-win32-x64-msvc` or similar fails, the scripts already use `ROLLUP_SKIP_NODEJS_NATIVE=1`; re-run `npm install` and `npm run dev`.

### Port conflicts

If port 5173 is in use, Vite will prompt for another port or you can set `--port` in the dev script.

### Clean install

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
npm install
npm run dev
```

---

## Workflow Checklist (Developer Discipline)

- **Before commit:** Run `npm run check` (test + build). Fix any failures.
- **Format/lint:** Run `npm run lint` if present.
- **Commit message pattern:** Short present-tense summary; e.g. `Add notifications page and command palette`.
- **Branch naming:** e.g. `feature/notifications`, `fix/alert-classifier`, `phase-8-6`.

### Pre-push suggestion

Run `npm run check` before pushing. Do not rely on CI alone; catch type and test failures locally. (Hooks are not enforced unless you add Husky.)

---

## How to Demo

1. **Start the app:** `cd frontend && npm run dev`. Open http://localhost:5173.
2. **Scenario dropdown:** Ensure run mode is **MOCK**. Use the scenario dropdown in the top bar to switch:
   - **S1 Trade ready (clean)** — Dashboard shows “Trade plan available”; Trade plan card with READY.
   - **S2 No trade (no setups)** — “No trade today”; no trade plan.
   - **S4 Risk hold (regime off)** — “Hold — exposure managed”; amber styling.
   - **S5 Trade blocked (earnings)** — Trade plan with BLOCKED status.
   - **S18 Stress** — History list with 250+ entries; Positions with 50+ rows; confirm list and filters stay responsive.
3. **History + detail drawer:** Go to **History**. Click a row to open the decision detail drawer (rationale, overview, trade plan if any, positions snapshot). Close with ESC or backdrop click.
4. **Notifications:** Go to **Notifications**. Use filters (All / Actionable / Warnings / Errors / Info) and search. Click a notification to open the detail drawer; use “Open position” if symbol present.
5. **Command palette:** Press **Ctrl+K** (or **Cmd+K** on Mac). Use search or click to navigate; in MOCK, change scenario; use “Open latest decision” or “Open &lt;symbol&gt; position”.
6. **Shortcuts:** Press **g** then **d** (dashboard), **g** **p** (positions), **g** **n** (notifications), **g** **h** (history).

---

## Data Mode

- **MOCK** (default): Data from scenario bundle (Dashboard, Positions, History, Notifications coherent).
- **LIVE**: Data from backend API (`VITE_API_BASE_URL`). If API is down or unreachable, pages show “LIVE data unavailable” and a system notification is added.

Switch via the MOCK/LIVE toggle in the top bar.

---

## LIVE Day 1 Observation Checklist

Use this on the first day you run the app against a LIVE backend.

1. **Backend up:** Start the backend; confirm `/api/healthz` returns 200 (if implemented).
2. **Env:** Set `VITE_API_BASE_URL` in `frontend/.env` (no trailing slash). Restart `npm run dev` after changing.
3. **Toggle LIVE:** Switch to LIVE in the top bar. Confirm **API: OK** (or **API: DOWN** if healthz missing).
4. **Dashboard:** If API is up, overview and decision banner should populate. If you see “LIVE data unavailable”, check logs and base URL.
5. **Positions / History / Notifications:** Open each; confirm data or clear empty/error state (no silent blank screen).
6. **Evaluated timestamp:** Status pill shows “Evaluated: &lt;date time&gt;” when backend provides it; “Stale” if older than 24h.
7. **No execution:** Confirm there are no trade/execute actions; UI is read-only.

---

## If Something Looks Wrong, Do THIS

1. **“LIVE data unavailable”** — Check `VITE_API_BASE_URL`, CORS, and backend logs. Ensure backend is running and endpoints return JSON.
2. **API: DOWN** — Backend may not expose `/api/healthz` or is unreachable. Fix base URL or backend; refresh.
3. **Empty lists (positions/history)** — Valid: backend can return `[]`. If you expected data, check backend DB and pipeline.
4. **Stale** — Evaluated timestamp &gt; 24h. Not a UI bug; run evaluation on the backend or treat as expected outside market hours.
5. **Schema mismatch / 500** — Check backend version and API contract. Run `npm run live:check` (with `LIVE_API_BASE_URL` set) to validate schemas.

---

## Do NOT Trade Checklist

- **This UI does not execute trades.** No buttons or actions send orders.
- **Do not use this UI as the sole signal to trade.** Use it for observation and decision context only.
- **If API is down or “LIVE data unavailable”, do not assume empty means “no positions” or “no alerts”.** Treat as unknown; verify elsewhere before any manual action.
- **Stale or missing “Evaluated” does not mean “no evaluation ran”.** Check backend and logs for evaluation status.

---

## Phase 10: LIVE Observability

### How polling works

- In **LIVE** mode the frontend polls read-only view endpoints (e.g. `/api/view/daily-overview`, `/api/view/positions`) every **60 seconds** so new evaluation snapshots appear without a full reload.
- Polling uses a `pollTick` from `PollingContext`; when the API is **DOWN**, the interval **backs off to 120 seconds** to avoid hammering a failing server.
- Polling only **re-fetches** view data; it does **not** trigger evaluation. Evaluation runs on the backend on a schedule (e.g. every 15 minutes during market OPEN) or via “Refresh now”.

### Refresh now (LIVE only)

- The **“Refresh now”** button in the top bar (LIVE only) sends a **POST** to `/api/ops/evaluate` with `{ reason: "MANUAL_REFRESH", scope: "ALL" }`.
- The backend runs a **DRY_RUN** evaluation (no orders); it returns a `job_id` and the frontend polls **GET /api/ops/evaluate/:job_id** until the job is `done` or `failed`, then re-fetches views.
- A **5‑minute cooldown** applies (per backend). If you hit cooldown, the UI shows “Try again in X min” and the button is disabled.
- Optional: set **`EVALUATE_TRIGGER_TOKEN`** (backend) and **`VITE_EVALUATE_TRIGGER_TOKEN`** (frontend) and send **`X-Trigger-Token`** header for POST; if the backend sets the env var and the header is missing/wrong, the request returns 403.

### Symbol diagnostics (Ticker Analysis)

- Go to **Analysis** (nav or `/analysis`). Available in **LIVE** only.
- Enter a symbol (e.g. **NVDA**) and click **Analyze**. The app calls **GET /api/view/symbol-diagnostics?symbol=NVDA**.
- You see: **recommendation** (ELIGIBLE / NOT_ELIGIBLE / UNKNOWN), **in universe**, **regime**, **risk posture**, **gates** (pass/fail + detail), **blockers**, **liquidity/options**, and **“Why not on dashboard?”** when not eligible.
- **Open in TradingView** links to `https://www.tradingview.com/symbols/NASDAQ-&lt;SYMBOL&gt;/` (no API keys).

### Troubleshooting “stale but API OK”

- **“Stale”** means the **last evaluated** decision timestamp is older than the threshold (e.g. 24h). **“API OK”** means `/api/healthz` (and optionally `/api/market-status`) responds.
- If the status pill shows **“Last market check”** newer than **“Last evaluated”** and **“No new decision”**, the backend **did** run a check but did **not** emit a new decision (e.g. no change, or skip reason). That is expected when nothing actionable changed.
- If you expect a new evaluation during market hours: (1) Confirm the backend scheduler/cron is running (e.g. 15‑min cadence during OPEN). (2) Use **Refresh now** once to force a DRY_RUN run (respects cooldown). (3) Check backend logs and **skip_reason** from `/api/market-status`.

### Required / optional env vars

| Env var | Where | Purpose |
|--------|--------|--------|
| **VITE_API_BASE_URL** | Frontend | Base URL for LIVE API (no trailing slash). Required for LIVE. |
| **EVALUATE_TRIGGER_TOKEN** | Backend | Optional. If set, POST `/api/ops/evaluate` requires header **X-Trigger-Token** with this value. |
| **VITE_EVALUATE_TRIGGER_TOKEN** | Frontend | Optional. If set, “Refresh now” sends **X-Trigger-Token** with this value. |

Do not hardcode secrets; use env only. GitHub health workflow notes remain unchanged.

---

## Scripts (Phase 9)

| Script | Purpose | How to run |
|--------|---------|------------|
| **Market health check** | Fetches LIVE endpoints, validates schema, writes report JSON. | From `frontend/`: `LIVE_API_BASE_URL=<url> npx tsx scripts/market-health-check.ts`. Optional: `ARTIFACTS_DIR=<path>`. |
| **Daily health report** | Reads health artifacts for a day; produces markdown + JSON summary. | From `frontend/`: `npx tsx scripts/daily-health-report.ts [YYYY-MM-DD]`. Output: `reports/daily/<date>.md`, `<date>.json`. |
| **Live schema test** | Integration-style tests against LIVE API (schema only). Skips if API not reachable. | `npm run live:check`. Set `LIVE_API_BASE_URL` or `VITE_API_BASE_URL`. |
| **CI health** | Typecheck + test + build. | `npm run ci:health` |

All scripts use Windows-safe paths (`path.join`). No secrets in repo; base URL from env.
