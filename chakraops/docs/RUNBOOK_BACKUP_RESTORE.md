# ChakraOps — Backup and Restore Runbook (R35.0)

Repository: `C:\Development\Workspace\ChakraOps-dev\chakraops`

All PowerShell scripts pin the approved **ChakraOps-dev** checkout and refuse the stale `C:\Development\Workspace\ChakraOps` path. Scripts call the canonical Python `backup_service` — backup policy is not duplicated in PowerShell. Environment variable **values are never printed**. `.env` is never read or included.

## Create backup

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops
.\scripts\backup_chakraops.ps1
.\scripts\backup_chakraops.ps1 -Label nightly
```

Or API: `POST /api/operations/backups/create`

**Policy:** SQLite via `sqlite3.Connection.backup()`; JSON/JSONL via writer-lock coordinated snapshots; `.env` and credentials excluded.

## List backups

```powershell
.\scripts\list_backups_chakraops.ps1
```

## Verify backup

```powershell
.\scripts\verify_backup_chakraops.ps1 -BackupId backup_manual_20260622T120000Z
```

Checks manifest presence, SHA-256 digests, and SQLite readability.

## Restore validation (non-destructive, temp only)

```powershell
.\scripts\restore_chakraops_validate.ps1 -BackupId <id>
```

Copies backup to `out/backups/restore_validate_<id>/` only. **Live restore is not automated.** Destructive restore requires explicit operator procedure outside these scripts.

## Retention cleanup — dry-run (default)

```powershell
.\scripts\cleanup_expired_backups.ps1
.\scripts\cleanup_expired_backups.ps1 -RetainCount 10
```

Shows `would_remove` / `would_retain` plan. **No deletion.**

## Retention cleanup — confirmed destructive

```powershell
.\scripts\cleanup_expired_backups.ps1 -Execute -ConfirmToken DELETE-EXPIRED-BACKUPS
```

Requires explicit confirmation token. Only eligible expired backup directories under `out/backups/` are removed. Live JSON/JSONL state and the decision database are never targets.

## Exclusions

- `.env` and credentials are never included in backups
- Automated scripts never perform live restore
- Backup root containment validated before any deletion

## Related runbooks

- Startup/shutdown: `RUNBOOK_STARTUP_SHUTDOWN.md`
- Scheduler operations: `RUNBOOK_SCHEDULER_OPERATIONS.md`
- Troubleshooting: `RUNBOOK_TROUBLESHOOTING.md`
