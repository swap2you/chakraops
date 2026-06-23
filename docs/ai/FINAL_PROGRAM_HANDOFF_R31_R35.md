# Final Program Handoff — R31–R35

Branch: `release/R31-R35-program`
Date: 2026-06-23

## Milestone commits

| Milestone | Commit | Summary |
|-----------|--------|---------|
| R31.0 | `7511c1b` | Repository, product, and live-data baseline |
| R32.0 | `dffa932` | Data reliability scope + C-1 ORATS remediation (`1223884`) |
| R33.0 | `ed9febd` | Canonical decision engine and profiles |
| R34.0 | `50aa600` | Live cutover, refresh safety, ORATS redaction (waiver `902a9cb`) |
| R35.0 | `18aa888`+ | Atomic consistency + Windows backup scripts + retention safeguards |

## Gates (final)

| Gate | R35 result |
|------|------------|
| Backend pytest | **1291 passed**, 2 skipped |
| Frontend tests | **335 passed**, 18 skipped |
| Frontend build | PASS |
| R35 targeted | **65 passed**, 1 skipped |

## UAT status

- Static audit: **complete**
- Technical reviews: **approved**
- Live Windows operational UAT: **pending**

## Trading safety

- Manual execution only
- No broker order routing
- ORATS sole provider; no silent fallback
- Schedules disabled by default until operator UAT approves enablement

## Daily operations

**Startup:** `C:\Development\Workspace\ChakraOps-dev\chakraops\scripts\start_chakraops.ps1`  
**Shutdown:** `C:\Development\Workspace\ChakraOps-dev\chakraops\scripts\stop_chakraops.ps1`  
**Runbooks:** `chakraops/docs/RUNBOOK_STARTUP_SHUTDOWN.md`, `RUNBOOK_SCHEDULER.md`, `RUNBOOK_BACKUP_RESTORE.md`

## Final PR

Do not open until **live Windows operational UAT** and operator approval. Codex and Claude final cross-process reviews approved with non-blocking notes. See `docs/ai/FINAL_PR_DESCRIPTION_R31_R35.md`.
