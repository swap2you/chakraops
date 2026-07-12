# R35.2 — Operational Hardening — Design

## 1. Stop-script redesign (`scripts/stop_chakraops.ps1`)

### Problem
The R35.0/R35.1 stop script authorized a kill only if the target process **command line contained the repo root**. Processes launched as `python -m uvicorn app.api.server:app --host 127.0.0.1 --port 18800` (module form) never carry the repo root in their command line, so the stop script refused to stop them. Verified pre-existing (base start script already used module form).

### Ownership record (already available)
`out/process_ownership.json` (written by `start_chakraops.ps1` via `process_ownership.write_record`) contains: `repo_root`, `backend_pid`, `frontend_pid`, `backend_cmd`, `frontend_cmd`, `backend_port`, `frontend_port`, `created_at`. The record itself is the primary authorization artifact (it is repo-scoped and written by our own start script).

### Multi-signal ownership decision (per role: backend, frontend)
A candidate PID is considered ChakraOps-owned and safe to stop when the record's `repo_root` matches the canonical checkout AND at least one strong identity signal holds, with fail-safe defaults:

Signals gathered per candidate PID:
- `S_PORT`: the PID (or a PID in its process tree) is currently LISTENING on the role's expected port from the record (`backend_port`/`frontend_port`).
- `S_CMD`: the process command line matches the role command regex (`uvicorn|python` for backend; `vite|npm|node` for frontend).
- `S_RECORD`: the PID equals the record's `backend_pid`/`frontend_pid`, OR is a descendant of it.
- `S_AGE`: the process `StartTime` is at/after the record `created_at` minus a small skew (guards PID reuse — a recycled PID would predate the record or be a foreign command).

Decision:
- If record missing → "nothing to stop" (exit 0).
- If record `repo_root` mismatches canonical checkout → REFUSE (exit 1), do not kill anything.
- Candidate PID set for a role = { record pid for that role } ∪ { current listener PID on the role's expected port }.
- For each candidate that is alive:
  - Safe-to-kill iff: `S_RECORD` OR `S_PORT`, AND `S_CMD`, AND NOT clearly-foreign. (Two independent signals required; `S_CMD` guards against killing an unrelated service that merely reused the PID or grabbed the port.)
  - Kill with `taskkill /PID <id> /T /F` (tree kill, so an `npm` launcher and its child `node`/`vite` both stop).
  - If alive but signals insufficient/ambiguous → REFUSE that PID, log "refusing (ambiguous ownership)".
- Idempotent: a not-running PID → log "already stopped", continue.
- Docker safety: expected ports are only 18800/18873 (or overrides from the record); port `8000` is never targeted, so Docker's host `:8000` is never touched.
- After processing both roles, `clear_record()`.

### Why this is safe
- Never kills by port alone (requires command identity too).
- Never kills by generic name alone (requires record/port linkage).
- Repo-root gate on the record prevents acting on a foreign checkout's record.
- Age signal guards PID reuse.
- Fail-safe: ambiguity → refuse, never force.

## 2. `docker compose config` real execution
`docker-compose.yml` `backend`/`caddy` services use `env_file: - .env` and Caddy requires `BASIC_AUTH_USER`/`BASIC_AUTH_HASH`. To run `docker compose config` for real without secrets:
- Provide transient non-secret env `BASIC_AUTH_USER`/`BASIC_AUTH_HASH` (throwaway values) for interpolation only.
- If root `.env` is absent, create a transient EMPTY `.env` solely to satisfy the `env_file` directive, run config, then remove ONLY that transient file (never touch a pre-existing `.env`).
- Assert mappings from the rendered config: backend `18800:8000`, frontend `18873:80`, VITE base `http://127.0.0.1:18800`, caddy prod-only.
No compose file changes; no committed env.

## 3. Documentation
Update `RUNBOOK_STARTUP_SHUTDOWN.md` (new stop behavior + module-form note + pre-UAT stack-up checklist) and `RUNBOOK_TROUBLESHOOTING.md` (stop guidance). Operational only; no strategy content.
