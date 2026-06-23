# Final Program Handoff — R31–R35

Branch: `release/R31-R35-program`  
Date: 2026-06-23  
Tested commit: `6804490`

## Milestone commits

| Milestone | Commit | Summary |
|-----------|--------|---------|
| R31.0 | `7511c1b` | Repository, product, and live-data baseline |
| R32.0 | `dffa932` | Data reliability scope + C-1 ORATS remediation (`1223884`) |
| R33.0 | `ed9febd` | Canonical decision engine and profiles |
| R34.0 | `50aa600` | Live cutover, refresh safety, ORATS redaction (waiver `902a9cb`) |
| R35.0 | `6804490` | Operational readiness, acceptance factory, Windows ops |

## Gates (final, parsed evidence 2026-06-23)

| Gate | R35 result |
|------|------------|
| Backend pytest | **1300 passed**, 4 skipped |
| Frontend tests | **335 passed**, 18 skipped |
| Frontend build | PASS |
| R35 targeted | **76 passed**, 1 skipped |
| Windows live smoke | PASS |
| Cowork browser UAT | **PASS WITH NOTES** |

## UAT status

- Static audit: **complete**
- Technical reviews: **approved**
- Windows operational smoke: **PASS**
- Cowork browser UAT: **PASS WITH NOTES** (2026-06-23)
- Data health: ORATS Degraded/WARN and Decision Store CRITICAL — **fails closed**; not claimed green

## Trading safety

- Manual execution only
- No broker order routing
- ORATS sole provider; no silent fallback
- Schedules disabled by default; **not enabled during program closure**

## Daily operations

**Startup:** `C:\Development\Workspace\ChakraOps-dev\chakraops\scripts\start_chakraops.ps1`  
**Shutdown:** `C:\Development\Workspace\ChakraOps-dev\chakraops\scripts\stop_chakraops.ps1`  
**Runbooks:** `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md`, `RUNBOOK_SCHEDULER_OPERATIONS.md`, `RUNBOOK_BACKUP_RESTORE.md`

## Final PR

Final PR created from `release/R31-R35-program` → `main`. **Not merged.** Merge, tag, deployment, and schedule enablement require separate operator approval. See `docs/ai/FINAL_PR_DESCRIPTION_R31_R35.md`.
