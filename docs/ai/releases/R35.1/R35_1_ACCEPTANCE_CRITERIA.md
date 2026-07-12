# R35.1 — Acceptance Criteria

**Release ID:** R35.1 · **Branch:** `release/R35.1-dedicated-ports-stabilization` · **Base:** `2c1393f`

All criteria must pass in Phase 3 before PR/merge. Evidence recorded under `out/verification/R35.1/notes.md`.

## A. Port single source of truth

- [ ] `chakraops/app/core/chakraops_ports.py` → `BACKEND_PORT == 18800`, `FRONTEND_PORT == 18873`.
- [ ] `scripts/chakraops_ports.ps1` → backend `18800`, frontend `18873` defaults.
- [ ] `frontend/vite.config.ts` and `frontend/vite.config.js` → dev server port `18873`, proxy `/api` → `http://127.0.0.1:18800`, `strictPort: true`, host `127.0.0.1`.
- [ ] Backend CORS default origin = `http://127.0.0.1:18873` (via `frontend_origin_default()`); overridable by `UI_CORS_ORIGINS`.
- [ ] `docker-compose.yml` host→container: backend `18800:8000`, frontend `18873:80`.

## B. Environment overrides (Phase 2 remediation)

- [ ] `CHAKRAOPS_BACKEND_PORT` honored by Python, Vite, **and** PowerShell.
- [ ] `CHAKRAOPS_FRONTEND_PORT` honored by Python, Vite, **and** PowerShell.
- [ ] Unset → defaults `18800` / `18873`.
- [ ] Invalid/empty/non-numeric/out-of-range → **clear failure** (or documented approved safe behavior).

## C. Local env-file safety

- [ ] `frontend/.env.development` is git-ignored and **not** committed.
- [ ] `.gitignore` does **not** contain an un-ignore (`!`) rule for `frontend/.env.development`.
- [ ] `frontend/.env.example` remains the committed template.
- [ ] Frontend starts with correct defaults when `frontend/.env.development` is **absent**.

## D. Stale old-port references

- [ ] Every remaining `8000`/`5173` classified (active defect / intentional container / historical / disabled legacy / false positive / test-comment).
- [ ] No **active** `8000`/`5173` defect remains in wired code paths.
- [ ] `frontend/src/test/liveEndpoints.e2e.test.ts` stale comment updated **only if authorized**.

## E. Validation gates

- [ ] Backend: `cd chakraops && python -m pytest tests -q --tb=short` (incl. `tests/test_chakraops_ports.py`).
- [ ] Frontend tests: `cd frontend && npm run test -- --run`.
- [ ] Frontend build: `cd frontend && npm run build`.
- [ ] PowerShell parse/StrictMode check of `scripts/chakraops_ports.ps1`, `start_chakraops.ps1`, `stop_chakraops.ps1`, `chakraops_common.ps1`, `health_check_chakraops.ps1`.
- [ ] Docker compose config validation (`docker compose config`).
- [ ] Runtime smoke: start on `18800`/`18873`, `GET /api/healthz` 200 (direct + Vite proxy), no active listener collision.
- [ ] Old-port detection: `18800`/`18873` free before start; `8000` may be Docker; no ChakraOps process on `8000`/`5173`.

## F. Governance / safety

- [ ] Scheduler disabled; recurring jobs disabled.
- [ ] `manual_only=true`; `trade_execution=false`; no broker-write.
- [ ] No `.env` committed; secrets redacted in all evidence.
- [ ] Only authorized paths modified; no forbidden path touched.
