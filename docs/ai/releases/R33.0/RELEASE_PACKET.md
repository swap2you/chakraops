# R33.0 Release Packet — Decision Engine, Strategy Profiles, and Risk Correctness

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 4 — trading-decision logic and financial risk

## Objective

Make ChakraOps recommendations mathematically consistent, profile-driven, portfolio-aware, and safely ranked.

## Dependencies

R32.0 trusted data contracts and freshness gates.

## Scope


Implement and validate regime gating, CSP, covered call, share-buy, stay-in-cash, ranking, sizing, earnings exclusion, position lifecycle, and Conservative/Balanced/Aggressive/Custom profiles. Decisions remain advisory and manual-only.


## Required deliverables


- canonical decision contract
- strategy profile schema and configuration
- CSP/CC/share-buy eligibility and scoring
- earnings blackout and event-risk gates
- portfolio allocation and position-sizing rules
- top 5–7 action ranking
- stay-in-cash outcome
- deterministic reason codes
- calculation/reference tests and scenario matrix
- strategy backtest fixtures for R34


## Allowed tracked paths

Exact paths only (from the R31 blueprint R33 section + R32 contracts). No generic domain-only permissions. The canonical decision engine is implemented as a single new package for strategy profiles and the decision input/output contract. R33 does NOT make it the authoritative live recommendation path; the legacy dual stacks (H-5) still drive the live surfaces and keep their existing guards. **H-5 remains OPEN and is owned by R34** (live cutover); no "superseded" claim applies to R33.

### New source — canonical decision engine

- `chakraops/app/core/decision_engine/__init__.py`
- `chakraops/app/core/decision_engine/profiles.py` (canonical profile config source; M-8)
- `chakraops/app/core/decision_engine/contract.py` (canonical decision input/output contract)
- `chakraops/app/core/decision_engine/gates.py` (regime/earnings/liquidity/holdings/cash/stale+missing gates; wires R32 `stale_data_gate`)
- `chakraops/app/core/decision_engine/strategies.py` (CSP/CC/share-buy eligibility + scoring + stay-in-cash)
- `chakraops/app/core/decision_engine/sizing.py` (portfolio-aware sizing + risk invariants)
- `chakraops/app/core/decision_engine/ranking.py` (deterministic scoring, tie-break, top 5–7, blocked/watch/cash separation)
- `chakraops/app/core/decision_engine/engine.py` (orchestration → canonical output)
- `chakraops/config/strategy_profiles.yaml` (operator-editable canonical profile config)
- `chakraops/app/api/decision_engine_routes.py` (read-only/advisory API, mounted under `/api/ui`)

### Modified source

- `chakraops/app/api/server.py` (include decision-engine router)
- `frontend/src/api/queries.ts` (read-only profile/decision query contract)
- `frontend/src/api/types.ts` (decision-engine types)

### Tests + fixtures

- `chakraops/tests/test_r330_profiles.py`
- `chakraops/tests/test_r330_contract.py`
- `chakraops/tests/test_r330_gates.py`
- `chakraops/tests/test_r330_strategies.py`
- `chakraops/tests/test_r330_sizing_invariants.py`
- `chakraops/tests/test_r330_ranking.py`
- `chakraops/tests/test_r330_golden_vectors.py`
- `chakraops/tests/test_r330_profile_matrix.py`
- `chakraops/tests/test_r330_stale_missing_data.py`
- `chakraops/tests/test_r330_decision_engine_api.py`
- `chakraops/tests/test_r330_backward_compat.py`
- `chakraops/tests/fixtures/r34_backtest/scenarios.json` (R34 backtest fixtures; no performance claims)
- `frontend/src/api/queries.decisionEngine.test.tsx`

### Docs / governance

- `docs/ai/releases/R33.0/{RELEASE_PACKET,STATUS,TOOL_LOG}.md`
- `docs/ai/PROGRAM_STATUS.md`
- `docs/master/CURRENT_STATE.md`
- `chakraops/docs/releases/R33.0_requirements.md`
- `chakraops/docs/releases/R33.0_release_notes.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`

Any additional tracked path requires operator approval and a packet update before editing.

## Forbidden paths and actions


- automatic orders
- broker writes
- undocumented leverage
- silent risk overrides
- live deployment
- broad page redesign


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Freeze canonical decision input/output contracts.
2. Implement profile configuration.
3. Correct CSP/CC/share-buy and cash logic.
4. Add portfolio-aware sizing and exposure caps.
5. Apply event/earnings/regime gates.
6. Implement ranking and top-action selection.
7. Add golden-reference calculations and scenario tests.
8. Validate position lifecycle transitions.



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

`out/verification/R33.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Golden test vectors for delta, DTE, premium, return, sizing, exposure, and ranking.
- Profile comparison matrix.
- Property/invariant tests: no impossible sizing, no uncovered CC, no CSP beyond reserved cash, no actionable result with missing critical data.
- Backtest fixtures must not claim future performance.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R33.0: Decision Engine, Strategy Profiles, and Risk Correctness`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
