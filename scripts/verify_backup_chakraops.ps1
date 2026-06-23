# ChakraOps — verify backup (R35.0)
param(
    [string]$BackupId = ""
)
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout

if (-not $BackupId) {
    $BackupId = python -c "from app.core.operations.backup_service import list_backups; b=list_backups(); print(b[0]['backup_id'] if b else '')"
    if ($LASTEXITCODE -ne 0 -or -not $BackupId) {
        Write-Error "No backups found; specify -BackupId"
        exit 1
    }
}

$escaped = $BackupId.Replace("'", "''")
python -c "import json; from app.core.operations.backup_service import verify_backup; print(json.dumps(verify_backup('$escaped'), indent=2))"
exit $LASTEXITCODE
