# PR Description — R34.0

## Summary
Consolidates the UI and adds trustworthy backtest, retention, and reporting workflows.

## Scope

Implement the approved navigation and page consolidation, remove duplicated information, fix table/DOM issues, present profile-aware decisions, harden backtest semantics, and establish lightweight retention/reporting. Preserve clear separation between live/manual decisions, simulations, and historical reports.


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
