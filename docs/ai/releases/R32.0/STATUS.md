# STATUS — R32.0

## Release
R32.0

## Branch
`release/R31-R35-program` (program milestone; single branch for R31–R35, milestone commits, one final PR)

## Objective
Make all market inputs observable, fresh, failure-classified, and suitable for downstream decisions.

## Risk level
Level 4 — market-data and decision-input correctness

## Current status
COMPLETE — C-1 ORATS secret remediation plus the full R32.0 data-reliability scope delivered and gate-verified. Reviews (Claude full + Codex full) deferred to consolidated post-R35 review per operator; checkpoint verdicts recorded below.

## Dependencies
R31.0 approved defect register and execution blueprint (operator-approved 2026-06-21).

## Cursor implementation
DELIVERED — C-1 security remediation:
- Hardcoded ORATS token removed; environment-only auth (`app/core/config/orats_secrets.py`, `get_orats_token`).
- Server lifespan env-based presence check + loud missing-token warning + redacted boot line; probe UNAVAILABLE when token absent.
- Misleading "hardcoded" wording fixed (`scripts/orats_smoke.py`, `README.md`).
- `.env`/`*.env` gitignored (verified); `.env.example` placeholder present; ignored local `.env` created from OS env (value never printed/committed).
- Test `tests/test_r320_orats_secret_env_only.py`.

DELIVERED — Claude non-blocking notes:
- Migrated runtime consumers from the import-time `ORATS_API_TOKEN` constant to `get_orats_token()` (orats_client, orats_opra, orats_equity_quote, orats_chain_pipeline, cc_chain_v2, csp_chain_v2, evaluation_service_v2, evaluation_store_v2, orats_daily_provider, ui_routes). `get_orats_token()` honors the module attribute so test patches stay compatible.
- `runtime.yaml` token field removed entirely so no literal placeholder can be read as a credential.
- Direct missing-token startup/provider-state test (`tests/test_r320_missing_token_startup.py`).

DELIVERED — R32.0 data-reliability scope:
- Freshness timestamps + stale-data blocking gate (`app/core/data_reliability/freshness.py`; M-10) — blocks actionable output on STALE/MISSING required inputs.
- Deterministic weekly universe refresh + history/reason codes (`app/core/universe/weekly_refresh.py`, `refresh_history_store.py`; M-4) — append-only JSONL history (no DB migration).
- Explicit event/earnings calendar AVAILABLE/UNAVAILABLE state (`app/core/data_reliability/event_calendar_status.py`; H-4) — no silent "no events == all clear".
- Provider health visibility, cache policy, retry/backoff + rate-limit surfacing, provider-failure classification, and read-only ORATS contract validation (`app/core/data_reliability/provider_health.py`).
- Read-only API (`app/api/data_reliability_routes.py`, mounted under `/api/ui`) + read-only frontend query contract (`frontend/src/api/queries.ts`, `types.ts`).
- No silent fallback provider; ORATS remains the sole provider.

## Claude review
Checkpoint (commit 1223884): APPROVED WITH NON-BLOCKING NOTES. Notes addressed in this milestone: (1) remaining consumers importing the import-time ORATS_API_TOKEN constant migrated to get_orats_token(); (2) runtime.yaml token-field literal `${ORATS_API_TOKEN}` made non-passable (removed/validated, fail-loud); (3) added direct missing-token startup/provider-state test. Full R32 review deferred to consolidated post-R35 review (operator decision 4).

## Codex review
Checkpoint (commit 1223884): BLOCKED — the R32 packet contained generic domain-only permissions, not the exact authorized file paths, before the 12-file commit. Remediation: RELEASE_PACKET.md now lists the exact paths changed by 1223884 plus the exact remaining-scope paths derived from the approved R31 blueprint; generic domain-only permissions removed; "any additional path requires operator approval + packet update" retained. Full R32 review deferred to consolidated post-R35 review (operator decision 4).

## Cowork UAT
Deferred to consolidated post-R35 UAT.

## Gates
- Backend: PASS — 1064 passed, 3 skipped
- Frontend tests: PASS — 311 passed, 18 skipped
- Frontend build: PASS — vite built in 10.04s (chunk-size warning only; M-13 bundle debt → R34)
- Release-specific validation: PASS — ORATS read-only smoke HTTP 200 / 6939 rows / redacted; missing-token loud/UNAVAILABLE; weekly-refresh determinism; stale-data blocking; event-calendar available/unavailable; secret regression scan clean. Evidence: `out/verification/R32.0/`.

## PR
Deferred. Single program PR after R35.0.

## Merge
Deferred.

## Tag
Deferred.

## Open blockers
- None for R32.0. Full Claude + Codex R32 review pending (consolidated post-R35 per operator).
- C-2, H-1, and later-milestone defects remain owned by R33.0–R35.0 per blueprint.
- M-13 (frontend bundle > 500 kB) remains; owned by R34.

## Next action
Await Claude and Codex full R32 review. Do not start R33.0 until approved.

## Stop point
Stopped after committing/pushing the R32.0 completion milestone. R33.0 not started.
