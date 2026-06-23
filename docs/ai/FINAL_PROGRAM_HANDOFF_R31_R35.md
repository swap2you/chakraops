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
| R35.0 | `18aa888` | Atomic cross-process consistency: occurrence claim, incident dedupe, backup writer locks |

Authorization commits: R35 Phase 0 `e20ccee`; R35 final consistency auth `6bd7a4e`; R35 run-id path waiver _(this docs commit)_.

### Operator waiver — run-id path authorization order (`18aa888`)

Paths modified in `18aa888` but not listed in preceding auth `6bd7a4e`:

- `chakraops/app/core/operations/job_executor.py`
- `chakraops/app/core/operations/job_run_store.py`

Backward-compatible optional `run_id` plumbing for atomic scheduled-occurrence claim. Operator waiver recorded; not retroactive; applies only to these two files in `18aa888`.

## External review (final cross-process)

| Reviewer | Verdict |
|----------|---------|
| Codex | APPROVED WITH NON-BLOCKING NOTES |
| Claude | APPROVED WITH NON-BLOCKING NOTES |
| Cowork UAT | Remaining release gate |

## Gates (final)

| Gate | R35 result |
|------|------------|
| Backend pytest | **1282 passed**, 1 skipped |
| Frontend tests | **335 passed**, 18 skipped |
| Frontend build | PASS |
| R35 targeted | **56 passed** |

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

Do not open until Cowork operational UAT and operator approval. Codex and Claude final cross-process reviews approved with non-blocking notes. See `docs/ai/FINAL_PR_DESCRIPTION_R31_R35.md`.
