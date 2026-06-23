# PR Description — R35.0

## Summary
Delivers operational scheduling, notifications, recovery, runbooks, and final UAT readiness.

## Scope

Implement and verify job scheduling, weekly universe refresh, EOD/nightly decision cycles, notifications, failure recovery, backups, health dashboards, startup/run scripts, operator runbooks, and final UAT. Deployment remains private/manual and must not enable trade execution.


## Validation
- Backend baseline gate
- Frontend test gate
- Frontend build gate
- Release-specific checks
- Claude review
- Codex review
- Cowork UAT

## Safety
- Manual-only trading preserved
- No broker order routing
- No silent fallback
- No secrets committed

## Rollback
Revert the release merge commit and restore required local data from documented backups.
