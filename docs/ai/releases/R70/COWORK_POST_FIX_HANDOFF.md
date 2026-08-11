# Cowork Post-Fix UAT Handoff (R70)

**Baseline for UAT:** current `origin/main` after R70 Full Defect Remediation (must be descendant of `dbe78de`).  
**Do not deploy.** **Do not begin R71.**

## Safety

manual_only · trade_execution=false · no broker writes · scheduler off · Stay in Cash valid

## What Cursor remediates (expect closed/verified)

- DEF-072 startup; DEF-070/071 gates
- Finance units (premium/OI/zero-truthiness/client return %)
- Eval exclusivity + ledger pointer (`ops/evaluate` → coordinator; `save_run`+latest)
- Paper excluded from live Dashboard open counts; score/hold-time SoT
- Monitor dedupe + notification sources honest when scheduler off
- AUTH-001 code path (local disabled default; production-like testable)
- Robinhood OAuth client code (live read needs owner browser auth)
- AI grounding (server-synthesized answers; golive LIVE risk from snapshots)
- Persistence honesty demotion + atomic writers + CI R70 gate

## Mandatory UAT scope

Follow library `prompts/90_COWORK_POST_FIX_UAT.md` fully. Independently rediscover routes. Recompute representative math. Capture screenshots/console/network (no secrets).

End marker: `COWORK R70 POST-FIX WHOLE-APPLICATION UAT COMPLETE`
