# LIVE Mode Debug Report

## Step 0 — Configuration and Evidence

### 1. LIVE base URL (VITE_API_BASE_URL)

- **Where it is read:** Frontend reads `VITE_API_BASE_URL` from Vite’s `import.meta.env` at runtime.
- **Files that use it:**
  - `frontend/src/data/apiClient.ts` — `API_BASE` is set from `import.meta.env.VITE_API_BASE_URL ?? ""`. All `apiGet`/`apiPost` calls build the full URL as `API_BASE + "/" + path` (path is e.g. `api/view/daily-overview`).
  - `frontend/src/hooks/useApiHealth.ts` — uses the same env for health checks.
  - `frontend/.env.example` — documents `VITE_API_BASE_URL=http://localhost:8000`.
- **How URL is built:** For a path like `/api/ops/evaluate`, `resolvePath` (in apiClient) does:  
  `base = API_BASE.replace(/\/$/, "")` then `url = base ? base + "/" + path.slice(1) : "/" + path`.  
  So with `VITE_API_BASE_URL=http://localhost:8000` you get `http://localhost:8000/api/ops/evaluate`.  
  If `VITE_API_BASE_URL` is unset, requests go to the same origin (e.g. `https://yourapp.com/api/...`). For local dev with API on port 8000 and frontend on 5173, you must set `VITE_API_BASE_URL=http://localhost:8000`.

### 2. Dev-only diagnostics

- **Full URL logging:** When `import.meta.env.DEV` is true or `VITE_DEBUG_API=true`, the frontend logs every LIVE request URL with `console.debug("[ChakraOps LIVE]", path, "->", fullUrl)` in `frontend/src/data/apiClient.ts`.
- **Resolved URL helper:** `getResolvedUrl(path)` is exported from `apiClient.ts` so dev tools or scripts can print the exact URL for any endpoint path (e.g. for scripting or debugging).

### 3. Endpoints that were failing (evidence)

| Endpoint | Status / Issue | Root cause |
|----------|----------------|------------|
| POST /api/ops/evaluate | 404 | Backend not running the FastAPI app that defines this route, or frontend using wrong base URL (same-origin without API). |
| GET /api/view/universe | 4xx/5xx or "Could not load universe" | Backend exception (e.g. persistence/import) or wrong base URL. |
| GET /api/view/symbol-diagnostics?symbol=SPY | 404 or "Analysis failed" | Route missing on server or frontend treating 200 + OUT_OF_SCOPE as error. |

**Fixes applied:**

- **Refresh now 404:** Backend already had POST `/api/ops/evaluate` and GET `/api/ops/evaluate/{job_id}` (unknown job returns 200 + `state: not_found`). Frontend now shows action-scoped error: "Refresh failed: 404 /api/ops/evaluate" and pushes a system notification with the failing URL so users know exactly which call failed.
- **Universe not loading:** Backend GET `/api/view/universe` always returns 200 with `{ symbols: [], updated_at }`. Frontend Analytics and Universe Summary now show "Universe unavailable (API error)" with retry on failure and emit a system notification; dev logs include endpoint + status when the call fails.
- **Ticker Analysis for SPY:** Backend GET `/api/view/symbol-diagnostics` returns 200 for any valid symbol (max length 12); OUT_OF_SCOPE returns `status: OUT_OF_SCOPE`, `fetched_at`, and full diagnostics. Frontend no longer shows "Analysis failed" for 200 responses; it shows the OUT_OF_SCOPE banner and renders diagnostics. Error copy distinguishes "Symbol not found or not in evaluation universe" for 404 vs "Not in evaluation universe" in the banner.
- **GET /api/view/trade-plan:** Added so this optional route never 404s; returns 200 with `{ trade_plan, fetched_at }`.

---

## Contract: Backend routes (FastAPI)

All routes are mounted on the app at the paths below (no extra prefix):

| Method | Path | Notes |
|--------|------|--------|
| GET | /api/healthz | ok |
| GET | /api/market-status | market_phase, last_evaluated_at, ... |
| GET | /api/view/daily-overview | + fetched_at |
| GET | /api/view/positions | array |
| GET | /api/view/alerts | as_of, items |
| GET | /api/view/decision-history | array |
| GET | /api/view/trade-plan | optional; 200, trade_plan, fetched_at |
| GET | /api/view/universe | symbols[], updated_at; always 200 |
| GET | /api/view/symbol-diagnostics?symbol=SYMBOL | 200, fetched_at, status (OUT_OF_SCOPE/UNKNOWN/…) |
| GET | /api/ops/status | last_run_at, next_run_at, cadence_minutes, ... |
| POST | /api/ops/evaluate | job_id, accepted; 403 if token required and wrong |
| GET | /api/ops/evaluate/{job_id} | state (queued|running|done|failed|not_found); always 200 |

Frontend `src/data/endpoints.ts` uses these exact paths with a base of `""`; the client prepends `VITE_API_BASE_URL`.

---

## CORS

Backend uses `CORSMiddleware` with `allow_origins=["*"]`. For production you can restrict to frontend origin(s) via env if needed; dev with Vite on 5173 and API on 8000 works with current setup.

---

## How to verify LIVE end-to-end

1. Set `VITE_API_BASE_URL` to your LIVE API (e.g. `http://localhost:8000`) and run the backend (e.g. `python -m scripts.run_api`).
2. In the UI: Refresh now → no 404; success or clear "Refresh failed: …" with URL.
3. Analytics → Universe loads or shows "Universe unavailable (API error)" with retry.
4. Analysis → enter SPY (or any symbol); result is shown (eligible or OUT_OF_SCOPE), no "Analysis failed" for 200.
5. CommandBar shows "Last evaluated at" and "Last data fetched at" (or equivalent timestamps) and tooltips for DRY_RUN and Stale.

---

## Definition of Done

**Commands to run:**

- **Frontend:** `npm run typecheck` — pass  
- **Frontend:** `npm run test` — pass (LIVE e2e tests skip unless `LIVE_API_BASE_URL` set)  
- **Frontend:** `npm run build` — pass  
- **Backend:** `pytest tests/test_api_phase10.py` — pass when FastAPI is installed (skipped otherwise)

**Manual verification (LIVE mode):**

- Refresh now → no 404; shows success or clear "Refresh failed: 404 /api/ops/evaluate" with system notification.  
- Analytics Universe → loads or shows "Universe unavailable (API error)" with Retry and system notification.  
- Analysis for SPY → returns result (eligible or OUT_OF_SCOPE) without "Analysis failed".  
- CommandBar → shows "Last evaluated" and "Last fetched" timestamps; tooltips for API OK, DRY_RUN, Stale, Conservative.
