# R35.1 — Dedicated-Port Stabilization: Scope

**Release ID:** R35.1
**Release branch:** `release/R35.1-dedicated-ports-stabilization`
**Base commit (validated R31–R35 baseline):** `2c1393ff31bf579708d8388e3a48d2092305a497`
**Authorization commit SHA:** _(placeholder — this documentation-only commit)_

---

## Background (factual record)

- R31–R35 were previously implemented, validated, and **merged to `main`** via PR #15 (merge commit `2c1393f`). Local `main` equals `origin/main`.
- While troubleshooting a "Failed to load universe" UI error, a **dedicated-port patch** (backend `18800`, frontend `18873`) was created **unintentionally in the dirty working tree of `main`**.
- **No patch changes were committed or pushed from `main`.** The work existed only as uncommitted working-tree modifications and untracked files.
- Phase 1 (this release) recovers that work onto `release/R35.1-dedicated-ports-stabilization` **without rewriting history** and **without losing or modifying** the changes.

## In scope

R35.1 is limited to:

1. **Dedicated-port stabilization** — establish a single source of truth for local dev ports (backend `18800`, frontend `18873`) across PowerShell, Python, Vite, Docker host mappings, CORS defaults, health/smoke/validation scripts.
2. **Environment-override correctness** — make `scripts/chakraops_ports.ps1` honor `CHAKRAOPS_BACKEND_PORT` / `CHAKRAOPS_FRONTEND_PORT` with safe fallback (Phase 2 remediation).
3. **Local environment-file safety** — ensure `frontend/.env.development` remains local and ignored; `.gitignore` must not un-ignore it; app must start when it is absent.
4. **Documentation consistency** — reconcile runbooks and playbooks to the dedicated ports; classify remaining `8000`/`5173` references.
5. **Validation** — unit tests, smoke, build, StrictMode/parse checks, Docker compose validation, evidence capture.

## Explicitly out of scope

- **R36 Universe or strategy implementation.**
- Strategy thresholds or recommendation-rule changes.
- Scheduler or recurring-job activation (remain disabled).
- Broker / order / Robinhood integration (trading remains manual-only; no broker-write).
- Broad Ruff/lint cleanup.
- Unrelated UI redesign.
- Committing any `.env` file (including `frontend/.env.development`).
- The unrelated `ChakraOps_Post_R35_R36_Prompt_Library.md`.

## Safety posture

- Scheduler and recurring jobs: **DISABLED**.
- Trading: **manual-only**; `trade_execution=false`; no broker-write capability.
- Secrets: never printed; no `.env` committed.
- Canonical checkout only: `C:\Development\Workspace\ChakraOps-dev\chakraops` (obsolete `C:\Development\Workspace\ChakraOps` not used).
