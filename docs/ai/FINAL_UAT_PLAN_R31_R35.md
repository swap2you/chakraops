# Final UAT Plan — R31–R35

## Completed

1. Claude/Codex technical reviews — approved
2. Cowork static audit — passed core safety invariants
3. Automated gates — backend 1291/2 skip; frontend 335/18 skip; build PASS

## Pending (final release gate)

1. **Live Windows operational UAT** — Cowork cannot execute PowerShell in Linux sandbox; operator must run on Windows
2. Daily startup/shutdown scripts on Windows (`scripts/start_chakraops.ps1`, `stop_chakraops.ps1`)
3. PowerShell backup scripts (`scripts/*_chakraops.ps1`, `cleanup_expired_backups.ps1`)
4. Operations panel on System Diagnostics
5. Manual job run (provider health, backup) — no auto-trading
6. Scheduler enablement requires explicit confirmation (`confirm=ENABLE`)
7. Canonical live recommendations (R34) still authoritative on Dashboard/Today
8. Stay in Cash valid outcome

## Not claimed

- Live operational UAT pass
- Recurring schedule enablement (remains disabled)

Evidence template: `out/verification/R35.0/final_uat_plan.md`
