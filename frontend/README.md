# ChakraOps Frontend (Phase 7.1)

Modern React + TypeScript shell for ChakraOps. Consumes read models (Phase 6.5) via mock JSON or future LIVE API.

## Requirements

- **Node.js 20 LTS** is required. Use the version in `frontend/.nvmrc` (e.g. 20.11.1).
- **Node 22 is unsupported** for now due to npm optional dependency resolution issues (e.g. `@rollup/rollup-win32-x64-msvc`). Use Node 20 LTS for a stable build.

If you use [nvm](https://github.com/nvm-sh/nvm) (or [nvm-windows](https://github.com/coreybutler/nvm-windows)):

```bash
cd frontend
nvm install    # installs version from .nvmrc
nvm use        # switches to that version
```

## Tech stack

- **React 18** + **TypeScript**
- **Vite** — build and dev server
- **TailwindCSS** — dark-first slate theme
- **shadcn-style** — Radix UI primitives (dropdowns), `cn()` utility
- **Framer Motion** — transitions
- **React Router** — `/dashboard`, `/positions`, `/analytics`, `/history`

## Run

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Default route is `/dashboard`.

### Build

```bash
npm run build
```

Requires `@types/node` and `tsconfig.node.json` with `"types": ["node"]` so `node:path` / `node:url` in `vite.config.ts` resolve.

### Rollup on Windows

The dev, build, and preview scripts set `ROLLUP_SKIP_NODEJS_NATIVE=1` so Rollup uses its JavaScript fallback instead of native binaries. This avoids `@rollup/rollup-win32-x64-msvc` resolution issues on Windows (npm optional dependency bugs) without downgrading Vite or Rollup. No UI or app behavior changes; the JS fallback is supported and deterministic.

### Clean install (Windows)

If you previously used Node 22 or see Rollup/native dependency errors, use Node 20 LTS and do a clean install:

1. Switch to Node 20 (e.g. `nvm use 20` or install Node 20 LTS from [nodejs.org](https://nodejs.org/)).
2. From the `frontend` directory, remove existing artifacts and reinstall:

   **PowerShell:**

   ```powershell
   Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
   Remove-Item -Force package-lock.json -ErrorAction SilentlyContinue
   npm install
   npm run dev
   ```

   **Cmd:**

   ```cmd
   rmdir /s /q node_modules 2>nul
   del package-lock.json 2>nul
   npm install
   npm run dev
   ```

## Data mode

- **MOCK** (default): Data comes from `/src/mock/*.json` (DailyOverviewView, PositionView[], TradePlanView, AlertsView).
- **LIVE**: Stubbed; no backend yet. Toggle in the top bar (MOCK / LIVE badge and button).

Env override: `VITE_DATA_MODE=MOCK` or `VITE_DATA_MODE=LIVE` (optional).

## Structure

```
frontend/
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css           # Tailwind + CSS variables (dark/light)
│   ├── lib/
│   │   └── utils.ts        # cn() for class names
│   ├── types/
│   │   └── views.ts        # DailyOverviewView, PositionView, TradePlanView, AlertsView
│   ├── mock/
│   │   ├── dailyOverview.json
│   │   ├── positions.json
│   │   ├── tradePlan.json
│   │   └── alerts.json
│   ├── data/
│   │   └── source.ts       # getDailyOverview, getPositions, getTradePlan, getAlerts (MOCK/LIVE)
│   ├── context/
│   │   ├── ThemeContext.tsx
│   │   └── DataModeContext.tsx
│   ├── components/
│   │   └── CommandBar.tsx  # Logo, strategy, view nav, badges, theme toggle, profile
│   └── pages/
│       ├── DashboardPage.tsx
│       ├── PositionsPage.tsx
│       ├── AnalyticsPage.tsx
│       └── HistoryPage.tsx
└── README.md
```

## App shell

- **Top command bar** (no sidebar): ChakraOps logo, strategy dropdown (Chakra only), view links (Dashboard / Positions / Analytics / History), run mode badge, risk posture badge, MOCK/LIVE toggle, theme toggle, profile dropdown.
- **Routing**: `/dashboard`, `/positions`, `/analytics`, `/history`; `/` redirects to `/dashboard`.
- **Theme**: Dark-first (slate); toggle switches `light` class on `<html>`.

No business logic; UI only reads data. No references to Streamlit or the legacy UI.

---

## Phase 8.5: Mock Scenarios

In **MOCK** mode you can switch between 18 scenario bundles to test all meaningful states and edge cases without editing JSON.

### How to switch scenarios

1. Ensure run mode is **MOCK** (top bar).
2. Use the **Scenario** dropdown in the command bar (visible only in MOCK).
3. Select a scenario (e.g. **S1 Trade ready (clean)**, **S8 History partial overview**, **S18 Stress**).
4. Dashboard, Positions, and History update coherently from that bundle.
5. Selection is stored in `localStorage` (`chakraops_mock_scenario`), so a refresh keeps your choice.

### How to run tests

```bash
cd frontend
npm install
npm run test
```

- **`npm run test`** — runs Vitest once (all `*.test.ts` / `*.test.tsx` under `src/`).
- **`npm run test:watch`** — runs Vitest in watch mode.
- **`npm run live:check`** — runs LIVE schema tests only (`src/test/liveSchema.test.ts`). Skips if `LIVE_API_BASE_URL` or `VITE_API_BASE_URL` not set or API unreachable.
- **`npm run ci:health`** — typecheck + test + build (e.g. for CI).

Tests include:

- Dashboard, History, Positions: render without errors; key headings and regions present.
- History: filtering by decision type; date filter empty state; clicking an entry opens the detail drawer.
- Positions: clicking a row opens the position detail drawer.
- Scenario registry: each scenario key has a valid bundle; S18 has 250+ history and 50+ positions; validator returns warnings (no throw).

### How to interpret diagnostics

1. In MOCK mode, click the **diagnostics** icon (stethoscope) in the command bar.
2. A right-side drawer opens with:
   - **Scenario** — current scenario name.
   - **Counts** — decisions, positions, alerts.
   - **Evaluation timestamp range** — min/max `evaluated_at` from decision history.
   - **Warnings** — list of soft validation issues (e.g. missing overview on a record, missing targets, high volume). Each warning has a code, message, and affected id/index.

Diagnostics are for developers only; no sensitive data. Use them to confirm scenario quality and coverage before wiring LIVE.

---

## Stock Universe & Evaluation Scope

- **Where it is defined:** The **backend** is the source of truth. The symbol universe lives in the ChakraOps SQLite DB table `symbol_universe` (see `chakraops/app/core/persistence.py`). On first run the backend seeds it with a default set (FAANG + SPY/QQQ). The Streamlit dashboard has a **Symbol Universe Manager** to add/edit symbols and enable/disable them.
- **What is used today:** Only symbols with `enabled = true` in `symbol_universe` are used for CSP candidate generation and evaluation. The default set is: **AAPL, MSFT, GOOGL, AMZN, META, SPY, QQQ**.
- **Type:** **Database-driven** with a baseline default. It is not hardcoded in the frontend; the frontend `src/config/universe.ts` is a **read-only reference** of the default set (for tooltips or labels). LIVE evaluation scope comes from the backend `/api/view/daily-overview` (e.g. `symbols_evaluated`) and backend DB.
- **Liquidity / screener:** Symbols are managed in the DB; no external screener is wired. Liquidity tier in `universe.ts` is for display only.

---

## Scripts (Phase 9)

- **`scripts/market-health-check.ts`** — Fetches LIVE API endpoints, validates schema, writes `artifacts/market_health_<date>_<time>.json`. Used by GitHub Actions (`.github/workflows/market-health.yml`). Run from `frontend/`: `LIVE_API_BASE_URL=<url> npx tsx scripts/market-health-check.ts`. Optional: `ARTIFACTS_DIR`, `MARKET_PHASE`.
- **`scripts/daily-health-report.ts`** — Reads health artifacts for a day; produces `reports/daily/<YYYY-MM-DD>.md` and `.json`. Run: `npx tsx scripts/daily-health-report.ts [YYYY-MM-DD]`. Optional: `ARTIFACTS_DIR`, `REPORTS_DAILY_DIR`.

All paths are Windows-safe. No secrets in repo; base URL from env.
