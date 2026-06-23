# ChakraOps — Backup and Restore Runbook (R35.0)

Repository: `C:\Development\Workspace\ChakraOps-dev\chakraops`

## Create backup

```powershell
cd C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops
.\scripts\backup_chakraops.ps1
```

Or: `POST /api/operations/backups/create`

## List backups

```powershell
.\scripts\list_backups_chakraops.ps1
```

## Verify backup

```powershell
.\scripts\verify_backup_chakraops.ps1 -BackupId backup_manual_20260622T120000Z
```

## Restore validation (non-destructive)

```powershell
.\scripts\restore_chakraops_validate.ps1 -BackupId <id>
```

Restores to a temporary path under `out/backups/restore_validate_*` only.

## Retention cleanup

```powershell
.\scripts\cleanup_expired_backups.ps1
```

Default retain count: 10. Active/current state is never deleted by automated cleanup.

## Exclusions

- `.env` and credentials are never included in backups
- Destructive live restore requires explicit operator approval outside automated tests
