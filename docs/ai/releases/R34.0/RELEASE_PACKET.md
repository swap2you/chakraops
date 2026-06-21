# R34.0 Release Packet — Unified Product Experience, Backtest, Database, and Reporting

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 3 — application refactor and analytical presentation

## Objective

Consolidate the operator experience around trusted decisions, positions, backtests, and reports.

## Dependencies

R33.0 canonical decision and profile contracts.

## Scope


Implement the approved navigation and page consolidation, remove duplicated information, fix table/DOM issues, present profile-aware decisions, harden backtest semantics, and establish lightweight retention/reporting. Preserve clear separation between live/manual decisions, simulations, and historical reports.


## Required deliverables


- consolidated navigation and page ownership
- dashboard/today/action-center flow
- portfolio and position lifecycle views
- universe/data-health views
- strategy profile controls
- backtest inputs, assumptions, and result labeling
- journal and monthly/weekly reports
- database migrations/retention policy
- CSV/export and backup/restore support
- performance and bundle improvements where justified


## Allowed tracked paths


Exact source/database/test paths must be copied from the R31 blueprint and R33 contracts. Expected domains:
- frontend routes/pages/components
- API query layer
- backtest service
- journal/reporting services
- database schema/migrations
- tests
- release/status/evidence docs


Any additional tracked path requires operator approval and packet update before implementation.

## Forbidden paths and actions


- changing strategy mathematics without R33 packet update
- broker order forms
- automated execution
- cosmetic redesign without workflow value
- destructive data migration without backup


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Define one-page ownership map.
2. Consolidate dashboard/today/analysis flows.
3. Consolidate positions/portfolio/wheel flows.
4. Separate universe administration from data health.
5. Harden backtest assumptions and labels.
6. Implement retention/reporting schema.
7. Fix known DOM nesting and high-value bundle issues.
8. Add migration, API, component, and end-to-end tests.



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

`out/verification/R34.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Database migration up/down or documented forward-only recovery.
- Backtest deterministic fixture checks.
- Reports reconcile with journal/position data.
- UI clearly labels delayed/live/simulated/historical states.
- No hidden duplicate primary workflow remains.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R34.0: Unified Product Experience, Backtest, Database, and Reporting`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
