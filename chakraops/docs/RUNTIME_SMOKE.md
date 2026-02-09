# Runtime Smoke Checklist

This document is the **pre-release and post-deploy smoke checklist**. Automate nothing at baseline — follow these steps manually. This becomes the canonical definition of “smoke passed” or “smoke failed.”

---

## When to Run Smoke

- Before tagging a release or cutting a baseline.
- After deploying backend or frontend to a target environment.
- After any change that could affect boot, health, or evaluation flow.

---

## Backend Smoke

### Without ORATS token

1. **Start backend** (from `chakraops`):  
   `python scripts/run_api.py` (or equivalent; ensure FastAPI/uvicorn installed).
2. **Health:**  
   - `GET /health` → 200, body e.g. `{"ok": true, "status": "healthy"}`.  
   - `GET /api/healthz` → 200, body e.g. `{"ok": true}`.
3. **Evaluation behavior:**  
   Trigger an evaluation (e.g. POST `/api/ops/evaluate-now` with API key if required, or run pipeline script). The system must **not** crash. Evaluation should complete or gracefully BLOCK with data-related reasons (e.g. required_data_missing, no ORATS data). No unhandled exception.

### With ORATS token

1. Set a valid `ORATS_API_KEY` (or equivalent) in the environment (e.g. from `.env` not in repo).
2. Start backend and run **one** evaluation.
3. **Confirm:**  
   - `required_data_missing` / `required_data_stale` populated when expected (e.g. when data is missing or stale).  
   - `data_sufficiency` reflects PASS / WARN / FAIL correctly per [data_sufficiency.md](./data_sufficiency.md).

---

## Frontend Smoke

1. **Build:**  
   From `frontend`: `npm run build`. Must complete successfully (warnings like chunk size are acceptable).
2. **Start dev server (or serve built assets):**  
   Load the app in a browser.
3. **Pages to load (no blank or crash):**  
   - Dashboard  
   - Ranked Universe  
   - One Ticker/Diagnostics page (e.g. enter a symbol and run analysis)  
   - Tracked Positions  
   - Decision Quality  
4. **BLOCKED / UNKNOWN behavior:**  
   - Where the API returns BLOCKED, the UI shows BLOCKED and reasons (e.g. risk_reasons, required_data_missing).  
   - Where data is missing, UNKNOWN appears (not blank or NA) for decision-critical fields (band, risk, strategy, price, return on risk when applicable).

---

## What Constitutes a Failed Smoke

- Backend does not start, or health endpoints return non-2xx or invalid body.
- Unhandled exception or crash when triggering evaluation (with or without ORATS).
- Frontend build fails.
- Any of the listed frontend pages fails to load or crashes.
- BLOCKED is not shown with reasons when the API indicates BLOCKED; or UNKNOWN is replaced by blank/NA for decision-critical data.

---

## Passing Criteria

- All backend steps (with and without ORATS) complete without crash; health OK; evaluation either succeeds or gracefully BLOCKS with data reasons.
- Frontend build succeeds; all listed pages load; BLOCKED/UNKNOWN behavior as above.

No automated script is required at baseline; this checklist is the definition of success.
