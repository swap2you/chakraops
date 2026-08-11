# ChakraOps Execution Runbook

> **R70+ operators:** use the canonical current runbook  
> [`docs/master/RUNBOOK_EXECUTION_CURRENT.md`](../../docs/master/RUNBOOK_EXECUTION_CURRENT.md).  
> This file is retained as a historical R24.8–R35 reference and may describe Caddy/BASIC_AUTH layouts that are **not** the preferred production topology.

Human runbook for clean-room startup, debugging, and troubleshooting. Reflects historical ChakraOps (R24.8–R35.0): dedicated dev ports, Docker, Caddy prod, /api routing, healthz, backup, offline proof harness.

**Related runbooks:** [RUNBOOK_STARTUP_SHUTDOWN.md](RUNBOOK_STARTUP_SHUTDOWN.md) · [RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md) · [VALIDATION_PLAYBOOK.md](VALIDATION_PLAYBOOK.md)

---

## Two-workspace workflow (stable vs dev)

- **ChakraOps-stable** — Runs daily from `main` or a release tag; use for production-like validation and EOD workflows.
- **ChakraOps-dev** — **Canonical dev checkout:** `C:\Development\Workspace\ChakraOps-dev\chakraops`. Used for release branches and feature work.
- **Do not use** `C:\Development\Workspace\ChakraOps` (stale); scripts and port config live in `ChakraOps-dev`.
- **Guidance:** Don’t open both workspaces in Cursor at once to reduce RAM; switch as needed.

---

## Canonical Store Path (ONE pipeline / ONE store)

**The canonical decision store path is:**
```
<REPO_ROOT>/out/decision_latest.json
```
- **REPO_ROOT** = parent of inner `chakraops/` package (e.g. `C:\Development\Workspace\ChakraOps-dev\chakraops`)
- All UI pages (Universe, Dashboard, Symbol) read from this store via v2 artifact only
- `scripts/run_and_save.py` and uvicorn both use this path regardless of current working directory

---

## Dedicated local ports

ChakraOps uses **non-default ports** so Docker and other dev tools on 8000/5173 do not conflict:

| Service | Port | URL |
|---------|------|-----|
| Backend API | **18800** | http://127.0.0.1:18800 |
| Frontend UI | **18873** | http://127.0.0.1:18873 |

Source of truth: `scripts/chakraops_ports.ps1`, `chakraops/app/core/chakraops_ports.py`, `frontend/.env.development`.

Preferred startup: `.\scripts\start_chakraops.ps1` from `ChakraOps-dev\chakraops`.

**Important:** Use **`127.0.0.1`**, not `localhost`, in URLs and proxy config. On Windows, `localhost` often resolves to IPv6 (`::1`) where Docker or other apps may already own port 8000.

---

## Golden Path (copy-paste)

### One-command startup (recommended)

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\start_chakraops.ps1
```

Open **http://127.0.0.1:18873/dashboard**. Shutdown: `.\scripts\stop_chakraops.ps1`.

### Full manual path (eval + backend + frontend)

**Repo root** (parent of `chakraops/` and `frontend/`):

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
```

**Backend package** (Python commands require `PYTHONPATH`):

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
```

```powershell
# Terminal 0: Activate venv, install deps
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
pip install -r requirements.txt

# Terminal 1: Generate decision artifacts (LIVE)
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out

# Full universe evaluation:
python scripts/run_and_save.py --all --output-dir out

# Terminal 2: Start backend (dedicated port 18800)
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Get-Location).Path
python -m uvicorn app.api.server:app --reload --host 127.0.0.1 --port 18800

# Terminal 3: Start React frontend (dedicated port 18873; reads frontend/.env.development)
cd C:\Development\Workspace\ChakraOps-dev\chakraops\frontend
npm install
npm run dev

# Terminal 4: Smoke checks (after backend is up)
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/healthz" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/system-health" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/decision/latest?mode=LIVE" -UseBasicParsing | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/universe" -UseBasicParsing -TimeoutSec 120 | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/symbol-diagnostics?symbol=SPY" -UseBasicParsing | Select-Object StatusCode

# Terminal 4b: Confirm Vite proxy (optional)
Invoke-WebRequest -Uri "http://127.0.0.1:18873/api/healthz" -UseBasicParsing | Select-Object StatusCode
```
Expected: StatusCode 200 for each smoke. **GET /api/healthz** is lightweight (no ORATS); **GET /api/ui/system-health** reports store path and frozen state.

---

## Docker Quickstart (dev)

From repo root:

```bash
docker compose up --build
```

- Frontend: **http://127.0.0.1:18873** (host maps to container :80)
- Backend: **http://127.0.0.1:18800** (host maps to container :8000)
- `out/` is bind-mounted so artifacts persist. No auth in dev.

---

## Production Quickstart (Caddy + basic auth)

From repo root:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile prod up -d --build
```

- Browser hits the same origin (e.g. `https://your-domain/`). All API calls use path **/api**; **Caddy proxies /api/\*** to the backend.
- Basic auth is required (set `BASIC_AUTH_USER`, `BASIC_AUTH_HASH` in server `.env`). See README for Caddy password hash.
- Canonical store path in container: `/workspace/out/decision_latest.json` (repo `out/` mounted).

---

## Offline Proof Harness (no network)

R25.1: Run the same evaluation pipeline with deterministic fixtures (no ORATS, no market data). Output is written to a **temp directory by default** (repo `out/` is not used).

From repo root:

```bash
python chakraops/scripts/offline_eval_proof.py --fixture chakraops/tests/fixtures/r25_1_offline_fixture.json
```

- Script prints `Output dir: <temp path>`; `decision_latest.json` and `eval_snapshot.json` are written there.
- Use `--output-dir out` to write into repo `out/` if needed. Use for hygiene/determinism checks and golden verification.

---

## Backup / Restore

- **Backup:** From repo root run `./scripts/backup_out.sh` (or `bash scripts/backup_out.sh`). Archives `out/` into `backups/` with retention (see script / README).
- **Restore:** Extract the backup tar into repo root so `out/` is restored as documented in README backup/restore steps.

---

## Where to find docs

| Purpose | Location |
|--------|----------|
| Startup / shutdown | [RUNBOOK_STARTUP_SHUTDOWN.md](RUNBOOK_STARTUP_SHUTDOWN.md) |
| Debugging / UI failures | [RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md) |
| PRD, roadmap, playbook, backlog, cleanup, architecture | `docs/master/` (e.g. ROADMAP_2026, RELEASE_PLAYBOOK, BACKLOG, CLEANUP_POLICY, REPO_ARCHITECTURE_MAP) |
| Per-release requirements, notes, checklist | `chakraops/docs/releases/` (e.g. R25.1_requirements.md, R25.1_release_notes.md, RELEASE_CHECKLIST.md) |
| Verification evidence (gate tails, UAT) | `out/verification/<Release>/notes.md` (e.g. out/verification/R25.1/notes.md) |

---

## Baseline freeze and stable/dev workflow

Use this when cutting a baseline (e.g. after R25.1) so **ChakraOps-stable** can run from a tag; **ChakraOps-dev** continues on a release branch or `main`.

### Pre-freeze

- [ ] **Git clean** — `git status` shows nothing to commit, working tree clean; all completed releases committed.
- [ ] **Gates** — Backend pytest, frontend test, frontend build passed for the releases being frozen (evidence in `out/verification/<Release>/notes.md` as needed).

### Operator checklist

- [ ] Merge current release branch into `main` (if using a release branch).
- [ ] Tag the baseline (e.g. `v25.1-baseline` or `v2026-baseline-01`).
- [ ] Push `main` and the tag to `origin`.

### Exact git commands (remote: origin, branch: main)

**Option A — Freeze current `main` (no merge):**

```bash
git checkout main
git pull origin main
git tag -a v25.1-baseline -m "Baseline freeze R25.1"
git push origin main
git push origin v25.1-baseline
```

**Option B — Merge release branch into `main`, then tag and push:**

```bash
git checkout main
git pull origin main
git merge release/r25.1 --no-ff -m "Merge release/r25.1 for baseline"
git tag -a v25.1-baseline -m "Baseline freeze R25.1"
git push origin main
git push origin v25.1-baseline
```

*(Replace `release/r25.1` with your release branch name and `v25.1-baseline` with your chosen tag.)*

### Stable vs dev after freeze

- **Stable clone:** Check out the baseline tag (e.g. `git checkout v25.1-baseline`) for production-like runs and EOD; do not pull latest `main` until the next baseline.
- **Dev clone:** Continue on `main` or a release branch for the next phase; avoid opening both workspaces in Cursor at once.

---

## Sanity Check

After running evaluation and starting the backend:
```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/sanity_one_pipeline.py
```

**Expected output (PASS):**
```
============================================================
Sanity: ONE pipeline / ONE store / store-first verification
============================================================
  [PASS] run_and_save.py --symbols SPY,AAPL --output-dir out
  [PASS] Store file exists, artifact_version=v2
  ...
============================================================
PASS: All sanity checks passed.
```

---

## Clean-Room Startup

1. **Kill ports (optional)** – if 18800/18873 are in use:
   ```powershell
   netstat -ano | findstr ":18800"
   netstat -ano | findstr ":18873"
   taskkill /PID <PID> /F
   ```

2. **Clear old artifacts (optional)** – to force fresh decision files:
   ```powershell
   Remove-Item out/decision_*.json -ErrorAction SilentlyContinue
   ```

3. **Generate artifacts** – only `scripts/run_and_save.py` produces decision snapshots.

4. **Start backend** then **frontend** (see Golden Path) — or use `.\scripts\start_chakraops.ps1`.

---

## Debug and troubleshooting

Full guide: **[RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md)**. Summary for common local-dev failures:

### Quick checks

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\health_check_chakraops.ps1
Invoke-WebRequest -Uri "http://127.0.0.1:18800/api/ui/universe" -UseBasicParsing -TimeoutSec 120 | Select-Object StatusCode
Invoke-WebRequest -Uri "http://127.0.0.1:18873/api/healthz" -UseBasicParsing | Select-Object StatusCode
```

### "Failed to load universe" (UI red error)

| Check | Command / action |
|-------|------------------|
| Backend up? | `http://127.0.0.1:18800/api/healthz` → 200 |
| Proxy up? | `http://127.0.0.1:18873/api/healthz` → 200 |
| Wrong server? | Do **not** use `localhost:8000` or `localhost:5173`; Docker often owns IPv6 :8000 |
| Vite config | Both `frontend/vite.config.ts` and `frontend/vite.config.js` must proxy to `127.0.0.1:18800` |
| Artifact exists? | Run `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out` |
| Slow load? | First `/api/ui/universe` with 171 symbols may take ~60–90s — wait for completion |

### Browser DevTools

1. **Network** → `/api/ui/universe` — note status (404 = wrong backend; 401 = UI key mismatch; 500 = server error)
2. **Console** — CORS errors → ensure backend allows `http://127.0.0.1:18873`

### Reset and restart

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\stop_chakraops.ps1
.\scripts\start_chakraops.ps1
```

---

## Troubleshooting Matrix

| Issue | Cause | Fix |
|-------|-------|-----|
| **Failed to load universe** / UI API errors | Vite proxy hit wrong server (`localhost` → Docker on :8000) or backend down | Use `127.0.0.1:18873` UI and `127.0.0.1:18800` API; restart via `start_chakraops.ps1`; see [RUNBOOK_TROUBLESHOOTING.md](RUNBOOK_TROUBLESHOOTING.md) |
| Port 18800 or 18873 in use | Another process bound | `netstat -ano \| findstr ":18800"` or `":18873"` → stop ChakraOps with `stop_chakraops.ps1` or free port |
| `/api/ui/universe` slow but eventually 200 | Full artifact rebuild per symbol | Normal for 171 symbols; wait up to ~90s |
| 401 on `/api/ui/*` | `UI_API_KEY` set without matching `VITE_UI_KEY` | Align keys in `chakraops/.env` and `frontend/.env`, or unset both for local dev |
| Missing decision files | Artifacts not generated | Run `python scripts/run_and_save.py --symbols SPY,AAPL --output-dir out` |
| `ModuleNotFoundError: No module named 'app'` | Wrong PYTHONPATH | From inner `chakraops/`: `$env:PYTHONPATH = (Get-Location).Path` |
| No module named uvicorn | Venv not activated | `.\.venv\Scripts\Activate.ps1` before running uvicorn |
| Stale checkout / wrong code | Using `ChakraOps` instead of `ChakraOps-dev` | Switch to `C:\Development\Workspace\ChakraOps-dev\chakraops` |
| UI shows MOCK in LIVE mode | MOCK data leaking | **STOP**. LIVE must only use `out/`; reject mock/scenario content. |

---

## Data Source Rules (LIVE vs MOCK)

- **LIVE:** Decision artifacts from `scripts/run_and_save.py` → `out/decision_*.json`, `out/decision_latest.json`.
- **MOCK:** Scenario data in `out/mock/` only. Strict separation.

---

## Canonical Store Path (ONE pipeline / ONE store)

The decision artifact has a **single canonical path** used by scripts, API, and scheduler:

```
<REPO_ROOT>/out/decision_latest.json
```

- **REPO_ROOT** = parent of inner `chakraops/` package (e.g. `C:\Development\Workspace\ChakraOps-dev\chakraops`).
- **Latest** is written **only** by `EvaluationStoreV2` when `evaluate_universe` or `evaluate_single_symbol_and_merge` runs.
- `scripts/run_and_save.py` writes timestamped copies to `--output-dir` but **never** writes `decision_latest.json` directly; the store does that.
- Server startup logs the resolved path: `[STORE] Canonical decision store path: ...`

---

## Sanity Script

Verifies ONE pipeline / ONE store invariants. Run after the backend is started.

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
$env:PYTHONPATH = (Get-Location).Path
python scripts/sanity_one_pipeline.py
```

The script:
1. Runs `run_and_save.py --symbols SPY,AAPL --output-dir out`
2. Reads the canonical store file
3. Calls API: `/api/ui/decision/latest`, `/api/ui/universe`, `/api/ui/symbol-diagnostics?symbol=SPY`
4. Verifies: `artifact_version == v2`, store vs API `pipeline_timestamp` match, universe/symbol-diagnostics score/band consistency

**Exit codes:**
- `0` – PASS
- `2` – SANITY FAIL

### SANITY FAIL: What it means and how to diagnose

| Message | Cause | How to diagnose |
|---------|-------|------------------|
| `run_and_save failed` | Evaluation or store write failed | Check stderr of run_and_save; ORATS/env issues |
| `Store file not found` | No artifact at canonical path | Run `run_and_save.py` first; check `[STORE] Canonical decision store path` at server startup |
| `decision/latest not v2` | API returned non-v2 or 404 | Ensure backend uses EvaluationStoreV2; restart server and re-run evaluation |
| `decision/latest metadata.pipeline_timestamp != store` | API serving stale or different artifact | Restart server so it loads the store; or API read from wrong path |
| `Universe SPY score/band == decision symbols SPY` fail | Universe and decision response disagree | Single store should be source; check ui_routes universe vs decision path |
| `symbol-diagnostics SPY vs store SPY` fail | Symbol-diagnostics not store-first | Check `_build_symbol_diagnostics_from_v2_store` uses store only |
| `API: Connection refused` / `Cannot reach API` | Server not running | Start backend on port 18800 before running sanity |

---

## If something looks wrong

- **Stale timestamps between endpoints** — API shows older `pipeline_timestamp` than the file on disk. Restart the server so it reloads the store, or rerun eval (e.g. `run_and_save.py` or `POST /api/ui/eval/run`) and re-check.
- **Module import errors** (`ModuleNotFoundError: No module named 'app'`) — Backend must run with `PYTHONPATH` set to the `chakraops` directory. From repo root: `cd chakraops` then `$env:PYTHONPATH = (Get-Location).Path` (PowerShell) or `export PYTHONPATH=$(pwd)` (bash) before running uvicorn or scripts.
- **Store CRITICAL** — `GET /api/ui/system-health` shows `decision_store.status === "CRITICAL"`. Store file missing, artifact not v2, or symbol(s) with null/invalid band. Run `run_and_save.py --symbols SPY,AAPL --output-dir out`, confirm `out/decision_latest.json` exists with `artifact_version` v2 and every symbol has band A/B/C/D and non-empty `band_reason`. See RUNBOOK_MARKET_LIVE.md “Decision store CRITICAL” for full steps.
