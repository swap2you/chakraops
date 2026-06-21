# R31.0 Release Packet — Repository, Product, and Live-Data Baseline

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 2 — repo-wide audit and planning

## Objective

Produce one trusted architecture map, live-data baseline, defect register, and executable blueprint for R32–R35.

## Dependencies

R30.8 merged and tagged.

## Scope


Read the full repository and current application behavior. Inventory backend, frontend, persistence, jobs, notifications, ORATS integration, universe logic, earnings/event handling, strategies, backtest, reports, and operational runbooks. Perform read-only live ORATS smoke checks through existing approved code paths when credentials are locally available. No product behavior changes.


## Required deliverables


- `docs/master/R31.0_REPOSITORY_PRODUCT_BASELINE_AUDIT.md`
- `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`
- `docs/master/R31.0_EXECUTION_BLUEPRINT.md`
- exact updates to current state, traveler, release ledger, status, and tool log
- local ORATS/data evidence under `out/verification/R31.0/`


## Allowed tracked paths


- `docs/master/R31.0_REPOSITORY_PRODUCT_BASELINE_AUDIT.md`
- `docs/master/R31.0_DEFECT_AND_GAP_REGISTER.md`
- `docs/master/R31.0_EXECUTION_BLUEPRINT.md`
- `docs/ai/PROGRAM_STATUS.md`
- `docs/ai/PROGRAM_MASTER_PLAN.md`
- `docs/ai/PROGRAM_ACCEPTANCE_MATRIX.md`
- `docs/ai/releases/R31.0/STATUS.md`
- `docs/ai/releases/R31.0/TOOL_LOG.md`
- `docs/master/CURRENT_STATE.md`
- `chakraops/docs/releases/R31.0_requirements.md`
- `chakraops/docs/releases/R31.0_release_notes.md`
- `chakraops/docs/releases/RELEASE_CHECKLIST.md`


Any additional tracked path requires operator approval and packet update before implementation.

## Forbidden paths and actions


- all backend/frontend source
- tests
- workflows
- runtime artifacts
- database content
- scheduler configuration
- deployment configuration
- secrets
- automatic or manual broker actions


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Repository and documentation truth audit.
2. Backend module and dependency map.
3. Frontend route/page/component inventory.
4. Decision engine and strategy inventory.
5. Persistence/reporting/backtest inventory.
6. Jobs/notifications/runbook inventory.
7. Read-only ORATS endpoint and data-availability smoke.
8. Defect register ranked Critical/High/Medium/Low.
9. Exact R32–R35 execution blueprint with file-level targets.



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

`out/verification/R31.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Confirm no tracked source changes.
- Confirm live checks are read-only and tokens are redacted.
- Confirm every critical/high issue has an owner release.
- Confirm R32–R35 packets remain compatible with audit findings or are updated explicitly.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R31.0: Repository, Product, and Live-Data Baseline`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
