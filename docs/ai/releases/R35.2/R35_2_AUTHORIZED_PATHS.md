# R35.2 — Authorized Paths (exact)

## Implementation (authorized to modify/create)
- `scripts/stop_chakraops.ps1` — rewrite stop logic (multi-signal, module-form, idempotent, fail-safe).
- `scripts/stop_ownership_selftest.ps1` — NEW local self-test harness (mock ownership records; no real kills of foreign processes).
- `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md` — document new stop behavior + pre-UAT stack-up checklist.
- `chakraops/docs/RUNBOOK_TROUBLESHOOTING.md` — stop-script guidance update.

## Governance (this authorization commit)
- `docs/ai/releases/R35.2/R35_2_SCOPE.md`
- `docs/ai/releases/R35.2/R35_2_DESIGN.md`
- `docs/ai/releases/R35.2/R35_2_AUTHORIZED_PATHS.md`
- `docs/ai/releases/R35.2/R35_2_RISK_REGISTER.md`
- `docs/ai/releases/R35.2/R35_2_ACCEPTANCE_CRITERIA.md`
- `docs/ai/releases/R35.2/R35_2_SELF_REVIEW_CHECKLIST.md`
- `docs/ai/validation/R35_2_ACCEPTANCE_MANIFEST.json`

## Forbidden (must NOT change)
- Any strategy/threshold/eligibility/ranking/sizing code.
- `chakraops/config/strategy_profiles.yaml` and the config threshold files.
- Scheduler/job code or enablement.
- Any broker/order/Robinhood surface.
- `docker-compose.yml` (execute config only; do not edit).
- `.env`, `frontend/.env.development`, prompt library.
- R36 explainability/universe code.

## Notes
- `docker compose config` is executed but NO compose/env file is committed; transient non-secret vars only.
- `scripts/stop_chakraops.ps1` was NOT modified by R35.1 (this is its first change since base) — no history rewrite.
- `chakraops/app/core/operations/process_ownership.py` is NOT modified (record already carries ports + created_at).
