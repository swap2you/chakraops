# Dev Execution Runbook — Stable/Dev Split and Release-Branch Workflow

**Purpose:** How to work in dev without breaking stable. Single source of truth for development setup, gates, and release flow.

**See also:** [ROADMAP_2026.md](ROADMAP_2026.md), [BACKLOG.md](BACKLOG.md), [RELEASE_PLAYBOOK.md](RELEASE_PLAYBOOK.md), [chakraops/docs/releases/RELEASE_CHECKLIST.md](../chakraops/docs/releases/RELEASE_CHECKLIST.md).

---

## Purpose

- **Stable** remains safe for daily use (main branch; no experimental changes).
- **Dev** is where release branches live; all feature work and verification happen there before merge to main.
- This runbook ensures you never accidentally break stable and that every release has gates + verification evidence.

---

## Folder model

| Workspace | Branch | Use |
|-----------|--------|-----|
| **ChakraOps-stable** | `main` | Daily use only. Run gates before any hotfix; no feature branches here. |
| **ChakraOps-dev** | `release/R25.x` (or current release branch) | Development. Create release branch off main; implement, gate, verify; open PR → merge to main. |

- Open **only one** of these in Cursor at a time to avoid OOM and wrong-repo edits.
- Do not create feature branches in the stable workspace.

---

## Git workflow

1. **Create release branch off main**
   - In ChakraOps-dev: `git checkout main && git pull && git checkout -b release/R25.x` (e.g. `release/R25.2`).
   - Confirm branch is created from main HEAD; no uncommitted changes required for branch creation, but keep commits atomic.

2. **Commit discipline**
   - Atomic commits: one logical change per commit.
   - Meaningful messages: e.g. `R25.2: add targets/stops lifecycle for shares`, not "fix" or "wip".

3. **Open PR → merge to main after gates and verification**
   - Run full gate (backend pytest, frontend test, frontend build).
   - Record evidence in `out/verification/<Release>/notes.md` (gitignored but required; paste or generate per RELEASE_CHECKLIST).
   - Open PR from `release/R25.x` → `main`; after review and gate pass, merge. Tag release if needed per RELEASE_PLAYBOOK.

---

## Dev environment setup

**Backend**

- From repo root (parent of `chakraops/` and `frontend/`): backend lives in `chakraops/` (Python).
  - `cd chakraops` (inner backend root)
  - `python -m venv .venv`
  - Windows: `.\.venv\Scripts\Activate.ps1` — Linux/Mac: `source .venv/bin/activate`
  - `pip install -r requirements.txt`

**Frontend**

- `cd frontend`
  - `npm ci` (preferred when lockfile present) or `npm install`

---

## Gates and evidence

**Gates (must be green before merge):**

1. **Backend:** `cd chakraops && python -m pytest -v --tb=short`
2. **Frontend tests:** `cd frontend && npm run test -- --run`
3. **Frontend build:** `cd frontend && npm run build`

**Evidence path:** `out/verification/<Release>/notes.md`

- Gitignored but **required** for each release. Paste gate outputs and UAT checklist; or use project scripts (e.g. R25.1 verification notes generator) and paste result. Do not commit `out/`; keep verification notes locally or in CI artifacts.

---

## How to run locally

**Backend**

- `cd chakraops` (inner backend root)
- Activate venv, then: `python -m uvicorn app.api.server:app --reload --port 8000`
- API base: http://localhost:8000

**Frontend**

- `cd frontend`
- `npm run dev`
- UI: http://localhost:5173 (Vite proxies `/api` to backend)

**Health checks**

- `GET http://localhost:8000/api/healthz` → 200
- `GET http://localhost:8000/api/ui/system-health` → 200

---

## Docker: dev vs prod (reference R24.8 / R24.9)

- **Dev compose:** Ports exposed (e.g. 8000 backend, 3000 frontend). Use for local debugging. See README Docker Quickstart.
- **Prod compose:** Caddy reverse proxy; same-origin `/api`; basic auth; only 80/443 exposed. See README Production Quickstart and `docker-compose.prod.yml`.

---

## Cursor OOM avoidance

- Open **only one repo** in Cursor at a time (stable **or** dev).
- Keep **.cursorignore** strict. Exclude:
  - `out/`
  - `node_modules/`
  - `frontend/dist/`
  - `.venv/`, `venv/`
  - `.pytest_cache/` and other caches

This reduces indexing and avoids accidental edits in large/generated trees.

---

*Last updated: R25.2 docs-only step. No code or decision-artifact changes in this runbook.*
