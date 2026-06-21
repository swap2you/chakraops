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
PARTIAL — C-1 ORATS secret remediation delivered and gate-verified; remaining data-reliability outcomes pending. Reviews deferred to post-R35 consolidated review per operator.

## Dependencies
R31.0 approved defect register and execution blueprint (operator-approved 2026-06-21).

## Cursor implementation
DELIVERED (C-1 subset):
- Hardcoded ORATS token removed; environment-only auth (`app/core/config/orats_secrets.py`, `get_orats_token`).
- Server lifespan env-based presence check + loud missing-token warning + redacted boot line; probe UNAVAILABLE when token absent.
- Misleading "hardcoded" wording fixed (`scripts/orats_smoke.py`, `README.md`).
- `.env`/`*.env` gitignored (verified); `.env.example` placeholder present.
- New test `tests/test_r320_orats_secret_env_only.py` (6 tests).
- Confirmed pre-existing: ORATS endpoint contracts/error classes; fail-fast, no silent fallback; redacted read-only smoke.

PENDING (not implemented this pass — must not be treated as done):
- Deterministic weekly universe refresh + history/reasons (M-4).
- Macro/earnings event-calendar adapter or explicit-unavailable surfacing (H-4).
- Freshness timestamps + stale-data blocking surfaced to API/UI (M-10).
- Cache/retry/rate-limit/provider-health observability surfacing.

## Claude review
Deferred to consolidated post-R35 review (operator decision 4).

## Codex review
Deferred to consolidated post-R35 review (operator decision 4).

## Cowork UAT
Deferred to consolidated post-R35 UAT.

## Gates
- Backend: PASS — 1023 passed, 3 skipped
- Frontend tests: PASS — 308 passed, 18 skipped
- Frontend build: PASS — tsc -b clean; vite 10.70s
- Release-specific validation: PARTIAL — ORATS smoke read-only + redacted PASS; missing-token loud/UNAVAILABLE PASS; refresh-determinism + stale-blocking PENDING

## PR
Deferred. Single program PR after R35.0.

## Merge
Deferred.

## Tag
Deferred.

## Open blockers
- C-2, H-1.. remain for later milestones per blueprint.
- R32.0 data-reliability outcomes remain to be implemented as a focused follow-up unit.

## Next action
Implement remaining R32.0 data-reliability outcomes (M-4, H-4, M-10, observability) as a focused, separately gate-verified unit, then proceed to R33.0.

## Stop point
Stopped after committing/pushing the C-1 security remediation milestone. Remaining R32.0 scope and R33.0–R35.0 require focused, individually-verified implementation; not fabricated.
