# PR Description — R33.0

## Summary
Delivers validated strategy profiles, decision correctness, risk sizing, and top-action ranking.

## Scope

Implement and validate regime gating, CSP, covered call, share-buy, stay-in-cash, ranking, sizing, earnings exclusion, position lifecycle, and Conservative/Balanced/Aggressive/Custom profiles. Decisions remain advisory and manual-only.


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
