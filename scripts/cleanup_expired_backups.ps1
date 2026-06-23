# ChakraOps — retention cleanup (dry-run by default) (R35.0)
param(
    [int]$RetainCount = 10,
    [switch]$Execute,
    [string]$ConfirmToken = ""
)
$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
$Backend = Join-Path $RepoRoot "chakraops"
$StaleRoot = "C:\Development\Workspace\ChakraOps"
$RequiredToken = "DELETE-EXPIRED-BACKUPS"

if (-not (Test-Path $RepoRoot)) { throw "Repository not found: $RepoRoot" }
if ((Get-Location).Path -like "$StaleRoot*") {
    throw "Stale checkout detected. Use $RepoRoot"
}
Set-Location $Backend

python -c "from app.core.operations.process_ownership import validate_repo_root; validate_repo_root(r'$RepoRoot')" | Out-Null

if ($Execute) {
    if ($ConfirmToken -ne $RequiredToken) {
        Write-Error "Destructive cleanup requires -Execute and -ConfirmToken $RequiredToken"
        exit 2
    }
    $py = @"
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
    $py = @"
import json
from app.core.operations.backup_service import cleanup_expired_backups
result = cleanup_expired_backups(retain_count=$RetainCount, dry_run=True)
print(json.dumps(result, indent=2))
"@
}

python -c $py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $Execute) {
    Write-Host "Dry-run only. Re-run with -Execute -ConfirmToken $RequiredToken to delete." -ForegroundColor Yellow
}
exit 0
