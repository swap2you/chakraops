# TOOL LOG — R35.0

## ChatGPT
- Program scope prepared.
- Status: packet ready.

## Cursor — Phase 0 authorization (2026-06-23)
- R34 closed and approved (Claude APPROVED WITH NON-BLOCKING NOTES; Codex APPROVED; Cowork PASS WITH NOTES).
- RELEASE_PACKET.md updated with exact tracked paths (job registry, scheduler service, job wrappers, notifications, backup, operations API/UI, Windows runbooks/scripts, tests, final handoff docs).
- STATUS.md set to ACTIVE; PROGRAM_STATUS and CURRENT_STATE updated.
- Docs-only commit `e20ccee` — `docs(R35.0): authorize operational-readiness paths`.

## Cursor — R35.0 implementation (2026-06-23)
- Phases 1–12: job registry, scheduler (disabled-by-default), job run store, executor, 8 job handlers, notifications dedupe, backup/restore, operations API, System Diagnostics ops panel, Windows scripts, runbooks, 12 test modules, final handoff pack.
- Legacy schedulers default disabled; master scheduler default disabled.
- Gates: backend 1248/3 skip; frontend 335/18 skip; build PASS.
- Milestone commit: `57b3939`.

## Reviews (post-57b3939)
- Claude: APPROVED WITH NON-BLOCKING NOTES (scheduler dedup, timeout, retry, notifications, EOD skip, SQLite backup, script safety).
- Codex: BLOCKED.
- Cowork: STOPPED (dirty working tree); operational UAT not performed.

## Cursor — final consistency authorization (2026-06-23)
- Codex BLOCKED (atomic occurrence claim, atomic incidents, backup writer locks); Cowork UAT paused.
- Waiver recorded for `test_r340_refresh_lock_ownership.py` in `fea0f69`.
- Docs-only commit `6bd7a4e`.

## Cursor — final consistency implementation (2026-06-23)
- Fix 1: atomic occurrence claim state machine (CLAIMED/COMPLETED/RELEASED)
- Fix 2: `open_incident_if_absent` + persisted notification dedupe
- Fix 3: `backup_writer_locks.py` — producer lock coordination
- Fix 4: full gate logs + multiprocess evidence
- Gates: backend 1282/1 skip; frontend 335/18 skip; build PASS; R35 suite 56 passed
- Implementation commit: `18aa888`; STATUS SHA: `ba529d3`

## Reviews — final cross-process (2026-06-23)
- Claude: **APPROVED WITH NON-BLOCKING NOTES** (governance note: run-id path waiver)
- Codex: **APPROVED WITH NON-BLOCKING NOTES**
- Technical R35 blockers: **closed**

## Cursor — final run-id path waiver (2026-06-23)
- Operator waiver for `job_executor.py` and `job_run_store.py` in `18aa888` (not listed in auth `6bd7a4e`)
- Docs-only commit precedes Cowork operational UAT

## Claude Code
- Final cross-process: APPROVED WITH NON-BLOCKING NOTES

## Codex
- Final cross-process: APPROVED WITH NON-BLOCKING NOTES

## Cursor — release acceptance factory authorization (2026-06-23)
- Retention-path waiver for `retention_cleanup_job.py` in `50919b4` recorded
- Docs-only commit precedes acceptance harness implementation

## Cursor — Windows operations hardening implementation (2026-06-23)
- Fix 1: PowerShell backup scripts (5) calling canonical Python backup_service
- Fix 2: retention dry-run + backup-root containment in cleanup_expired_backups
- Fix 3: RUNBOOK_SCHEDULER_OPERATIONS.md + RUNBOOK_BACKUP_RESTORE.md updated
- Fix 4: test_r350_retention_safety.py + gates; evidence under out/verification/R35.0/
- Gates: backend 1291/2 skip; frontend 335/18 skip; build PASS; R35 suite 65/1 skip

## Claude Cowork
- Static audit: passed core safety invariants
- Live operational UAT: NOT RUN (PowerShell unavailable in sandbox) — **remaining gate**

## Operator
- R35.0 START authorized. Schedules disabled by default until final UAT approves enablement.
