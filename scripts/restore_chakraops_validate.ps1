# ChakraOps — restore to temp for validation only (R35.0)
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupId
)
$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
$Backend = Join-Path $RepoRoot "chakraops"
$StaleRoot = "C:\Development\Workspace\ChakraOps"

if (-not (Test-Path $RepoRoot)) { throw "Repository not found: $RepoRoot" }
if ((Get-Location).Path -like "$StaleRoot*") {
    throw "Stale checkout detected. Use $RepoRoot"
}
Set-Location $Backend

python -c "from app.core.operations.process_ownership import validate_repo_root; validate_repo_root(r'$RepoRoot')" | Out-Null

$py = @"
import json
from app.core.operations.backup_service import restore_to_temp
result = restore_to_temp('$BackupId')
print(json.dumps(result, indent=2))
if not result.get('ok'):
    raise SystemExit(1)
"@

python -c $py
exit $LASTEXITCODE
