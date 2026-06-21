# R32.0 Release Packet — Market Data, Earnings, Universe, and Freshness Reliability

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 4 — market-data and decision-input correctness

## Objective

Make all market inputs observable, fresh, failure-classified, and suitable for downstream decisions.

## Dependencies

R31.0 approved defect register and execution blueprint.

## Scope


Implement approved R31 findings for ORATS request reliability, endpoint contracts, earnings/event availability, universe refresh, cache/freshness policy, data quality, and diagnostics. Use ORATS as the sole active options provider. Any non-ORATS source for market calendar or public earnings metadata must be explicitly approved, labeled, and never used as a silent options-data fallback.


## Required deliverables


- live ORATS contract tests and redacted evidence
- endpoint inventory and failure classification
- earnings/event calendar adapter or explicit unavailable state
- deterministic weekly universe refresh with audit log
- freshness timestamps and stale-data gates
- cache policy and retry/backoff observability
- data-quality diagnostics in API/UI contracts
- runbook for provider failure and stale data


## Allowed tracked paths

Exact paths only (copied from the approved R31 execution blueprint). No generic domain-only permissions.

### Already changed by commit `1223884` (C-1 ORATS secret remediation)

- `chakraops/README.md`
- `chakraops/app/api/server.py`
- `chakraops/app/core/config/orats_secrets.py`
- `chakraops/config/runtime.yaml`
- `chakraops/scripts/orats_smoke.py`
- `chakraops/tests/test_r320_orats_secret_env_only.py`
- `chakraops/docs/releases/R32.0_requirements.md`
- `chakraops/docs/releases/R32.0_release_notes.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`
- `docs/ai/PROGRAM_STATUS.md`
- `docs/ai/releases/R32.0/STATUS.md`
- `docs/ai/releases/R32.0/TOOL_LOG.md`

### Remaining R32.0 scope — new source

- `chakraops/app/core/data_reliability/__init__.py`
- `chakraops/app/core/data_reliability/freshness.py`
- `chakraops/app/core/data_reliability/provider_health.py`
- `chakraops/app/core/data_reliability/event_calendar_status.py`
- `chakraops/app/core/universe/weekly_refresh.py`
- `chakraops/app/core/universe/refresh_history_store.py`
- `chakraops/app/api/data_reliability_routes.py`

### Remaining R32.0 scope — modified source (Claude-note token migration + router include + event-calendar status)

- `chakraops/app/api/server.py`
- `chakraops/app/api/ui_routes.py`
- `chakraops/app/core/environment/event_calendar.py`
- `chakraops/app/core/options/v2/csp_chain_v2.py`
- `chakraops/app/core/options/v2/cc_chain_v2.py`
- `chakraops/app/core/orats/orats_client.py`
- `chakraops/app/core/orats/orats_equity_quote.py`
- `chakraops/app/core/orats/orats_opra.py`
- `chakraops/app/core/options/orats_chain_pipeline.py`
- `chakraops/app/core/eval/evaluation_service_v2.py`
- `chakraops/app/core/eval/evaluation_store_v2.py`
- `chakraops/app/core/eligibility/providers/orats_daily_provider.py`

### Remaining R32.0 scope — tests

- `chakraops/tests/test_r320_freshness.py`
- `chakraops/tests/test_r320_weekly_refresh.py`
- `chakraops/tests/test_r320_event_calendar_status.py`
- `chakraops/tests/test_r320_provider_health.py`
- `chakraops/tests/test_r320_missing_token_startup.py`
- `chakraops/tests/test_r320_data_reliability_api.py`

### Remaining R32.0 scope — frontend (read-only data contract only; no UI redesign)

- `frontend/src/api/queries.ts`
- `frontend/src/api/types.ts`
- `frontend/src/api/queries.dataReliability.test.tsx`

### Docs / governance

- `docs/ai/releases/R32.0/RELEASE_PACKET.md`
- `docs/master/CURRENT_STATE.md`
- `docs/ai/releases/R34.0/RELEASE_PACKET.md` (R34 persistence-decision guardrail, Step 5)
- `docs/ai/PROGRAM_MASTER_PLAN.md` (R34 persistence-decision guardrail, Step 5)

Any additional tracked path requires operator approval and a packet update before editing.

## Forbidden paths and actions


- broker modules
- order execution
- unrelated strategy scoring
- broad UI redesign
- provider substitution without operator approval
- secrets or raw tokens


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Normalize ORATS endpoint contracts and errors.
2. Add freshness metadata and stale blocking.
3. Implement earnings/event source contract.
4. Implement weekly universe refresh and history.
5. Add cache/retry/rate-limit observability.
6. Surface data-quality reasons.
7. Add unit, contract, integration, and live read-only smoke tests.



## Mandatory baseline gates

Before `DONE`, run exactly:

```powershell
cd chakraops
python -m pytest tests -q --tb=short

cd ..\frontend
npm run test -- --run
npm run build
```

Store local evidence under:

`out/verification/R32.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Live read-only ORATS smoke on approved symbols.
- Missing credentials must produce SKIPPED/UNAVAILABLE, never fake PASS.
- Verify no network test leaks secrets.
- Verify universe refresh is deterministic from the same inputs.
- Verify stale data cannot produce an actionable recommendation.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R32.0: Market Data, Earnings, Universe, and Freshness Reliability`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
