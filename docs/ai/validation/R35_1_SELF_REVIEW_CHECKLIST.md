# R35.1 — Self-Review Checklist

**Release ID:** R35.1 · **Branch:** `release/R35.1-dedicated-ports-stabilization` · **Base:** `2c1393f`

## Phase 1 — Authorization (this phase)

- [x] Verified no drift: branch `main`, HEAD `2c1393f`, `origin/main` equal, nothing staged.
- [x] Reconciled inventory: **28** modified tracked, **3** untracked impl/test, **1** local-only, **1** unrelated.
- [x] `.env.development` secret scan: only port variables, no secret-like names, no credential-like values.
- [x] Created `release/R35.1-dedicated-ports-stabilization` from `2c1393f` via `git switch -c` (no stash/reset/clean).
- [x] All 28 modified + 5 untracked files survived; nothing staged; HEAD unchanged.
- [x] `ChakraOps_Post_R35_R36_Prompt_Library.md` added to `.git/info/exclude` (not deleted).
- [x] Governance docs authored (8 files).
- [ ] Only the 8 governance files staged; verified via `git diff --cached --name-only`.
- [ ] Documentation-only authorization commit created.
- [ ] Working tree intentionally remains dirty (port impl still uncommitted).

## Phase 2 — Remediation (do NOT perform in Phase 1)

- [ ] `scripts/chakraops_ports.ps1` honors `CHAKRAOPS_BACKEND_PORT` / `CHAKRAOPS_FRONTEND_PORT` with fallback 18800/18873 and fail-fast on invalid.
- [ ] `.gitignore` restored so `frontend/.env.development` stays ignored (no `!` un-ignore).
- [ ] App starts with defaults when `.env.development` absent.
- [ ] Stale `8000`/`5173` references classified; `liveEndpoints.e2e.test.ts` comment updated if authorized.
- [ ] Only authorized paths touched.

## Phase 3 — Validation

- [ ] Backend pytest incl. `test_chakraops_ports.py`.
- [ ] Frontend test + build.
- [ ] PowerShell parse/StrictMode.
- [ ] Docker compose config validation.
- [ ] Runtime smoke on 18800/18873.
- [ ] Evidence in `out/verification/R35.1/notes.md`.

## Safety (all phases)

- [ ] Scheduler disabled; recurring jobs disabled.
- [ ] `manual_only=true`; `trade_execution=false`; no broker-write.
- [ ] No `.env` committed; secrets redacted.
- [ ] No R36 / strategy / threshold changes.
