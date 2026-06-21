# R35.0 Release Packet — Operations, Scheduling, Notifications, UAT, and Readiness

## Branch

`release/R31-R35-program`

R31–R35 are sequential milestones on this single program branch, not separate PR branches. The program uses one branch, five milestone commits, and one final PR opened only after R35.0 is complete.

## Risk level

Level 3 — operational reliability and release readiness

## Objective

Make ChakraOps reliable for daily personal use with observable jobs, clear alerts, recovery procedures, and validated end-to-end workflows.

## Dependencies

R34.0 unified product flow and trusted reporting.

## Scope


Implement and verify job scheduling, weekly universe refresh, EOD/nightly decision cycles, notifications, failure recovery, backups, health dashboards, startup/run scripts, operator runbooks, and final UAT. Deployment remains private/manual and must not enable trade execution.


## Required deliverables


- jobs inventory and enabled/disabled policy
- scheduler observability and idempotency
- weekly universe refresh schedule
- EOD/nightly refresh and report schedule
- notification routing, formatting, dedupe, and persistence
- backup/restore and retention operations
- health and failure dashboard
- startup/shutdown/runbook
- full operator UAT report
- private hosting readiness decision
- final known-issues disposition


## Allowed tracked paths


Exact source/config/test paths must be copied from the R31 blueprint and prior release contracts. Expected domains:
- scheduler/jobs
- notifications
- health/diagnostics
- scripts
- backup/restore
- optional private deployment configuration
- tests
- release/status/evidence docs


Any additional tracked path requires operator approval and packet update before implementation.

## Forbidden paths and actions


- public unauthenticated hosting
- automatic broker actions
- write-capable brokerage integration
- unattended financial execution
- secrets in repository
- enabling every existing job without review


Locked:
- No auto-trading.
- No broker order routing.
- No silent data fallback.
- No secrets in logs or committed evidence.
- No unrelated refactor.

## Implementation workstreams


1. Inventory and classify all jobs.
2. Implement idempotent schedules and locks.
3. Repair notification pipeline and message clarity.
4. Add failure/retry/dedupe observability.
5. Validate backup/restore and retention.
6. Harden startup/run scripts.
7. Complete full browser and operational UAT.
8. Produce go-live/private-use readiness report.



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

`out/verification/R35.0/`

At minimum:

- `notes.md`
- `backend_pytest.log`
- `frontend_test.log`
- `frontend_build.log`

Risk-specific checks add to these gates; they never replace them.


## Release-specific validation


- Time-controlled scheduler tests.
- Duplicate-run/idempotency tests.
- Notification golden-message tests.
- Backup/restore rehearsal.
- 24-hour or accelerated operational soak where feasible.
- No job may submit or simulate a broker order as a side effect.


## Review requirements

- Cursor implementation and STEP report.
- Claude Code architecture review for Level 2+.
- Codex independent review.
- Cowork UAT when this packet defines UAT.
- Operator approval before PR merge and tag.

## PR title

`R35.0: Operations, Scheduling, Notifications, UAT, and Readiness`

## Rollback

Revert the release commit or merge commit. Preserve local evidence and database backups. Never rewrite shared history.

## Stop point

Stop after approved scope, gates, evidence, reviewer verdicts, and PR preparation. Do not merge or tag without operator approval.
