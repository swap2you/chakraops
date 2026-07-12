# R35.1 — Design

**Release ID:** R35.1
**Branch:** `release/R35.1-dedicated-ports-stabilization`
**Base SHA:** `2c1393ff31bf579708d8388e3a48d2092305a497`

This document describes the intended end-state for the dedicated-port patch. It does **not** authorize implementation beyond the exact paths in `R35_1_AUTHORIZED_PATHS.md`. Phase 2 performs the remediation.

---

## 1. Single source of truth for ports

| Layer | File | Backend | Frontend |
|-------|------|---------|----------|
| PowerShell | `scripts/chakraops_ports.ps1` | 18800 | 18873 |
| Python | `chakraops/app/core/chakraops_ports.py` | 18800 | 18873 |
| Vite dev | `frontend/.env.development` (+ `vite.config.ts/js`) | proxy → 18800 | 18873 |
| Docker (host→container) | `docker-compose.yml` | 18800→8000 | 18873→80 |

Backend default assertion: **18800**. Frontend default assertion: **18873**.

## 2. Required Phase 2 remediation

### A. PowerShell environment overrides (PRIMARY Phase 2 defect)

`scripts/chakraops_ports.ps1` currently **hardcodes** `18800`/`18873` and does **not** read environment overrides. Phase 2 must:

- Honor valid `CHAKRAOPS_BACKEND_PORT` and `CHAKRAOPS_FRONTEND_PORT`.
- Fall back to backend **18800**, frontend **18873** when unset.
- For invalid/empty/non-numeric/out-of-range values (valid TCP range 1–65535; recommend rejecting privileged/ephemeral edge cases per design): **fail clearly with an explicit error** rather than silently binding a wrong port. (Fail-fast is the approved safe behavior; document any deviation.)

This aligns PowerShell with the Python (`os.getenv(... , default)`) and Vite (`loadEnv`) layers, which already honor the overrides.

### B. Local environment-file safety

- `frontend/.env.development` remains **local-only and git-ignored**; never committed.
- `.gitignore` must **not** un-ignore it. The current working-tree `.gitignore` change added `!frontend/.env.development` (un-ignore) — Phase 2 must **restore** the ignore rule so the file cannot be committed.
- `frontend/.env.example` remains the committed example/template.
- The application/frontend must **start correctly when `frontend/.env.development` is absent** (Vite defaults to 18800/18873 via `vite.config.*`).

### C. Stale old-port references — classification

Every remaining `8000`/`5173` occurrence must be classified as one of:

| Reference | Classification |
|-----------|----------------|
| `docker-compose.yml` `"18800:8000"` | Intentional Docker **container** port (correct) |
| `frontend/src/test/liveEndpoints.e2e.test.ts` comment `LIVE_API_BASE_URL=http://localhost:8000` | Stale **test/example comment** — update in Phase 2 **only if this path is authorized** |
| `chakraops/scripts/legacy_disabled/*.py` | **Disabled legacy code** — not wired |
| test fixtures (`open_interest=8000`, `$38000`, OCC option symbols) | **False positives** (not ports) |
| runbook historical mentions already converted | **Historical evidence** where applicable |

## 3. Runtime rationale

Docker Desktop (`com.docker.backend.exe`) listens on `127.0.0.1:8000`, which collided with the previous default backend port and caused the "Failed to load universe" proxy failure. Moving to `18800`/`18873` removes the collision. Ports `18800`/`18873` are currently free.

## 4. Non-goals

No strategy, scheduler, broker, or R36 work. See `R35_1_SCOPE.md`.
