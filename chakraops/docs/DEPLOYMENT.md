# Deployment (Phase 7): Vercel + Railway, private access

This document describes how to deploy ChakraOps as an always-on private app: backend on Railway, frontend on Vercel, with authentication boundaries and no public access by default.

## Overview

- **Backend (Railway):** FastAPI app; API key required for all non-health routes; scheduler runs on startup; `/health` is public for health checks.
- **Frontend (Vercel):** Static build; optional password gate; API base URL and API key from env; no credentials in repo, no hardcoded URLs.
- **No evaluation or alert logic changes** — only auth and deployment wiring.

## Backend (Railway)

### Required environment variables

Set these in the Railway project (Settings → Variables). **Do not commit them.**

| Variable | Required | Description |
|----------|----------|-------------|
| `CHAKRAOPS_API_KEY` | Yes (for auth) | Secret key; clients must send it as `X-API-Key`. If unset, no API key is required (suitable only for local dev). |
| `ORATS_API_TOKEN` | Yes | ORATS API token (from [orats.com](https://orats.com)). Used for options data. |
| `UNIVERSE_EVAL_MINUTES` | No | Scheduler interval in minutes (1–120). Default: 15. |
| `SLACK_WEBHOOK_URL` | No | Slack webhook for Phase 6 alerts. If unset, alerts are logged only. |
| `NIGHTLY_EVAL_TIME` | No | Nightly run time, e.g. `19:00`. Default: 19:00. |
| `NIGHTLY_EVAL_TZ` | No | Timezone, e.g. `America/New_York`. |
| `OPENAI_API_KEY` | No | For TTS on Strategy page. |

### Railway setup steps

1. **Create a project** in [Railway](https://railway.app). Add a new service.
2. **Connect the repo** (e.g. GitHub). Set root directory to the backend root (e.g. `chakraops/` if the repo has frontend and backend in one repo, or the folder that contains `app/`, `config/`, `requirements.txt`).
3. **Build command:**  
   - If using a single repo with `chakraops/` as backend: e.g. `pip install -r requirements.txt` (run from `chakraops/` if you set it as root).  
   - Or use a `Dockerfile` that installs deps and runs uvicorn.
4. **Start command:**  
   `uvicorn app.api.server:app --host 0.0.0.0 --port $PORT`  
   Railway sets `PORT`; use it so the app listens on the correct port.
5. **Set env vars** (see table above). At minimum: `CHAKRAOPS_API_KEY`, `ORATS_API_TOKEN`. Optionally set `PORT` if Railway does not set it (usually automatic).
6. **Health check:** In Railway, set the health check path to `/health` (GET). No authentication; returns `{"ok": true, "status": "healthy"}`.
7. **Deploy.** Note the public URL (e.g. `https://your-app.railway.app`). You will use this as the frontend API base URL.

### API key behavior

- When `CHAKRAOPS_API_KEY` is set, **every** request must include header `X-API-Key` with that value, **except**:
  - `GET /health`
  - `GET /api/healthz`
- Missing or wrong key → `401` with `{"detail": "Missing or invalid X-API-Key"}`.
- When `CHAKRAOPS_API_KEY` is **not** set (e.g. local dev), no API key is required.

### Scheduler

- The evaluation scheduler starts on app startup and runs every `UNIVERSE_EVAL_MINUTES` minutes (only when market is open, per existing logic).
- Nightly scheduler runs at `NIGHTLY_EVAL_TIME` in `NIGHTLY_EVAL_TZ` if enabled.
- No extra cron or worker is required; both run inside the same process.

---

## Frontend (Vercel)

### Required environment variables

Set these in Vercel (Project → Settings → Environment Variables). Use **Production** (and Preview if you want). **Do not commit them.**

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_APP_PASSWORD` | Recommended | Password or token to unlock the app (access gate). If unset, no gate is shown. |
| `VITE_API_BASE_URL` | Yes (when API is on Railway) | Full API URL, e.g. `https://your-app.railway.app`. No trailing slash. |
| `VITE_API_KEY` | Yes (when backend uses API key) | Same value as `CHAKRAOPS_API_KEY`; sent as `X-API-Key` on every request. |

### Vercel setup steps

1. **Create a project** in [Vercel](https://vercel.com). Import the repo.
2. **Root directory:** Set to the frontend folder (e.g. `frontend/` if the repo has a `frontend` subfolder with `vite.config.ts`, `package.json`).
3. **Build command:** `npm run build` (or `pnpm build` / `yarn build`).
4. **Output directory:** `dist` (Vite default).
5. **Set env vars:**  
   - `VITE_API_BASE_URL` = your Railway API URL (e.g. `https://your-app.railway.app`).  
   - `VITE_API_KEY` = same as Railway `CHAKRAOPS_API_KEY`.  
   - `VITE_APP_PASSWORD` = a strong password or token for the access gate (optional but recommended).
6. **Deploy.** The site will be static; no server-side secrets. Env vars are baked into the build (so do not put backend-only secrets in Vite env that you would not want in the client bundle; `VITE_API_KEY` is expected to be the same as the backend key and is in the client — the real protection is the backend requiring the key and the gate limiting who can open the app).

### Access gate

- If `VITE_APP_PASSWORD` is set, the app shows a password/token prompt before rendering the UI. On success, state is stored in `sessionStorage` for the session.
- If unset, the app renders immediately (useful for local dev or if you rely only on API key).

### Build and static assets

- Build is standard Vite: `npm run build` produces static files in `dist/`. No server-side rendering; Vercel serves the SPA. Ensure your Vite config does not reference localhost-only URLs; use `VITE_API_BASE_URL` for the API.

---

## Required env vars summary

**Railway (backend)**  
- `CHAKRAOPS_API_KEY` — required for production (enables API key auth).  
- `ORATS_API_TOKEN` — required for data.  
- Others as above (scheduler, Slack, etc.).

**Vercel (frontend)**  
- `VITE_API_BASE_URL` — Railway API URL.  
- `VITE_API_KEY` — same as `CHAKRAOPS_API_KEY`.  
- `VITE_APP_PASSWORD` — optional access gate.

---

## Rotating keys

1. **API key (`CHAKRAOPS_API_KEY` / `VITE_API_KEY`):**  
   - Generate a new secret (e.g. long random string).  
   - Update `CHAKRAOPS_API_KEY` on Railway and redeploy (or restart).  
   - Update `VITE_API_KEY` on Vercel and redeploy the frontend.  
   - Old key stops working as soon as backend is updated.
2. **App password (`VITE_APP_PASSWORD`):**  
   - Change in Vercel env and redeploy. Users will need the new password on next load (sessionStorage is per-tab/session).
3. **ORATS / Slack / OpenAI:**  
   - Rotate in the respective dashboards and update the corresponding env vars on Railway; redeploy or restart.

---

## Cost expectations

- **Railway:** Depends on plan and usage (CPU/memory/time). Free tier has limits; always-on services typically need a paid plan. Check [Railway pricing](https://railway.app/pricing).
- **Vercel:** Frontend is static; free tier is usually sufficient for low traffic. Check [Vercel pricing](https://vercel.com/pricing).
- **ORATS / Slack / OpenAI:** Per each provider’s terms. No cost change from ChakraOps deployment itself.

---

## Common failure modes

| Symptom | Likely cause | Fix |
|--------|----------------|-----|
| 401 on all API calls | Missing or wrong `X-API-Key`; or `CHAKRAOPS_API_KEY` not set on Railway but frontend sends a key | Ensure backend and frontend use the same key; if backend has no key set, frontend should not send one (leave `VITE_API_KEY` unset). |
| CORS errors from browser | Backend not allowing frontend origin | Backend uses `allow_origins=["*"]`; if you lock this down, add your Vercel origin to CORS. |
| Health check failing | Wrong path or auth | Use `GET /health` (no auth). Do not use `/api/healthz` for Railway if you want to avoid sending a key in the health check. |
| Scheduler not running | App not starting or crashing | Check Railway logs; ensure `uvicorn` runs with `--host 0.0.0.0 --port $PORT` and deps install correctly. |
| Frontend shows “API error” or network error | Wrong `VITE_API_BASE_URL` or API down | Verify Railway URL and that `/health` returns 200. Ensure no trailing slash in `VITE_API_BASE_URL`. |
| Access gate not showing | `VITE_APP_PASSWORD` not set in Vercel | Set it in project env and redeploy (Vite env is build-time). |
| Build fails on Vercel | Missing deps or wrong root | Ensure root is the frontend folder and `npm run build` runs successfully locally with the same Node version. |

---

## No credentials in repo / no hardcoded URLs

- All secrets (API key, ORATS token, Slack, app password, etc.) come from **environment variables** in Railway and Vercel.
- Do **not** commit `.env` or any file containing these values. Use `.env.example` with placeholder names only (e.g. `CHAKRAOPS_API_KEY=your-secret-here`).
- API base URL is **only** `VITE_API_BASE_URL` in the frontend; no hardcoded production URLs in code.

---

## Quick reference

- **Backend health (no auth):** `GET /health`  
- **Backend API (with key):** All other routes require `X-API-Key: <CHAKRAOPS_API_KEY>`.  
- **Frontend gate:** Set `VITE_APP_PASSWORD` to require a password before the app loads.  
- **Frontend → API:** Set `VITE_API_BASE_URL` and `VITE_API_KEY` so the SPA talks to Railway with the correct key.
