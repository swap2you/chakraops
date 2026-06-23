# Final UAT Plan — R31–R35

## Completed

1. Claude/Codex technical reviews — approved
2. Cowork static audit — passed core safety invariants
3. Automated gates — backend **1300/4 skip**; R35 targeted **76/1 skip**; frontend **335/18 skip**; build PASS (2026-06-23 harness)
4. **Cursor Windows operational smoke** — PASS (`scripts/run_r31_r35_live_smoke.ps1`; log `out/verification/R35.0/windows_live_smoke.log`)
5. PowerShell backup scripts — exercised in live smoke (create/list/verify/restore-validate/cleanup dry-run)
6. Internal adversarial self-reviews A/B/C — PASS (`out/verification/R35.0/self_review/`)

## Pending (final release gate)

1. **Cowork browser-only UAT** — see `docs/ai/validation/R31_R35_COWORK_UAT_HANDOFF.md` (no PowerShell)
   - Operations page scheduler/job disabled display
   - Boolean ORATS presence only
   - No broker controls
   - Dashboard/Today canonical recommendations
   - Symbol Diagnostics fail-closed
   - Manual-only wording; Stay in Cash; backtest warning
   - Pagination; console errors; network credential leakage check

## Not claimed

- Cowork browser UAT pass
- Recurring schedule enablement (remains disabled)
- Final PR or deployment

Evidence: `out/verification/R35.0/`
