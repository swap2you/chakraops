# ChakraOps — retention cleanup (dry-run by default) (R35.0)
param(
    [int]$RetainCount = 10,
    [switch]$Execute,
    [string]$ConfirmToken = ""
)
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout

$RequiredToken = "DELETE-EXPIRED-BACKUPS"

if ($Execute) {
    if ($ConfirmToken -ne $RequiredToken) {
        Write-Error "Destructive cleanup requires -Execute and -ConfirmToken $RequiredToken"
        exit 2
    }
    python -c @"
import json
from app.core.operations.backup_service import cleanup_expired_backups, CLEANUP_CONFIRM_TOKEN
result = cleanup_expired_backups(
    retain_count=$RetainCount,
    dry_run=False,
    confirm=True,
    confirm_token=CLEANUP_CONFIRM_TOKEN,
)
print(json.dumps(result, indent=2))
"@
} else {
    python -c @"
import json
from app.core.operations.backup_service import cleanup_expired_backups
result = cleanup_expired_backups(retain_count=$RetainCount, dry_run=True)
print(json.dumps(result, indent=2))
"@
}

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $Execute) {
    Write-Host "Dry-run only. Re-run with -Execute -ConfirmToken $RequiredToken to delete." -ForegroundColor Yellow
}
exit 0
