# PR Description — R32.0

## Summary
Stabilizes ORATS, earnings/events, universe refresh, freshness, and data-quality behavior.

## Scope

Implement approved R31 findings for ORATS request reliability, endpoint contracts, earnings/event availability, universe refresh, cache/freshness policy, data quality, and diagnostics. Use ORATS as the sole active options provider. Any non-ORATS source for market calendar or public earnings metadata must be explicitly approved, labeled, and never used as a silent options-data fallback.


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
