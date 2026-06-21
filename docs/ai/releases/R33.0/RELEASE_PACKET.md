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


Exact source/test paths must be copied from R31 blueprint and R32 contracts before work. Expected domains:
- decision engine
- eligibility/scoring
- strategy configuration
- portfolio/risk
- positions lifecycle
- API schemas
- tests and fixtures
- release/status/evidence docs


Any additional tracked path requires operator approval and packet update before implementation.

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
