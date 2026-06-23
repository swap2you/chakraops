# Final UAT Plan — R31–R35

## Completed (2026-06-23, commit `6804490`)

1. Claude/Codex technical reviews — approved
2. Cowork static audit — passed core safety invariants
3. Automated gates — backend **1300/4 skip**; R35 targeted **76/1 skip**; frontend **335/18 skip**; build PASS
4. Cursor Windows operational smoke — PASS
5. PowerShell backup scripts — exercised in live smoke
6. Internal adversarial self-reviews A/B/C — PASS
7. **Cowork browser-only UAT — PASS WITH NOTES**
   - Scheduler master disabled; all recurring jobs disabled; no scheduled job fired
   - ORATS boolean only; manual_only=true; trade_execution=false
   - No broker/order endpoint or UI control
   - Dashboard/Today canonical recommendations; Symbol Diagnostics fail-closed
   - Stay in Cash valid; backtest simulation warning; pagination; no console errors; no credential leakage

## Accepted non-blocking notes

1. ORATS Degraded/WARN and Decision Store CRITICAL are current data-health states; product fails closed (not claimed green).
2. Some Cowork screenshots blank (capture limitation); DOM, page text, API, console, and network validation passed.

## Not performed (by design)

- Recurring schedule enablement (remains disabled)
- Deployment
- Merge or tag (separate operator decisions after PR review)

Evidence: `out/verification/R35.0/` including `cowork_browser_uat.md` (local; not committed)
