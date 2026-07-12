# R35.2 Acceptance Criteria

## Stop-script behavior
- [ ] Stops a default-form stack (backend `python -m uvicorn` on 18800, frontend `npm run dev`/node on 18873) started via `start_chakraops.ps1`.
- [ ] Stops an override-port stack (e.g., 19900/19973).
- [ ] Idempotent: second `stop` run reports "already stopped"/"nothing to stop", exit 0.
- [ ] Partial start (only backend up) stops the running role and reports the other as already stopped.
- [ ] Refuses to kill when ownership record `repo_root` mismatches canonical checkout.
- [ ] Never kills Docker (`com.docker.backend` on :8000 survives).
- [ ] Never kills an unrelated Python/Node process not matching record+command identity (fail-safe refuse).
- [ ] After stop, role ports are free and ownership record cleared.

## Docker
- [ ] Real `docker compose config` executes (exit 0) with transient non-secret vars.
- [ ] Rendered mappings: backend `18800:8000`, frontend `18873:80`, VITE base `http://127.0.0.1:18800`, caddy prod-only.
- [ ] No committed compose/env change; transient `.env` removed if created; pre-existing `.env` untouched.

## Quality gates
- [ ] PowerShell parse + StrictMode for all `scripts/*.ps1` (0 failures).
- [ ] Stop self-test harness passes.
- [ ] Backend `pytest tests` green; frontend tests + build green (regression guard).
- [ ] Secret scan of diff clean; `.env` not committed.
- [ ] Authorization/changed-path validation: only authorized paths changed.
- [ ] Safety: manual_only=true, trade_execution=false, scheduler/recurring disabled, no broker-write.

## Process
- [ ] Architecture + adversarial reviews GO (blockers/high resolved).
- [ ] Evidence under `out/verification/R35.2/`.
- [ ] One PR; CI green; merge; post-merge validation on main green.
