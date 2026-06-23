# ChakraOps — create backup (R35.0)
param(
    [string]$Label = "manual"
)
$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"

if (-not (Test-Path $RepoRoot)) { throw "Repository not found: $RepoRoot" }
if ((Get-Location).Path -like "$StaleRoot*") {
    throw "Stale checkout detected. Use $RepoRoot"
}
Set-Location $Backend

python -c "from app.core.operations.process_ownership import validate_repo_root; validate_repo_root(r'$RepoRoot')" | Out-Null

$py = @"
import json
from app.core.operations.backup_service import create_backup
result = create_backup(label='$Label')
print(json.dumps({'backup_id': result['backup_id'], 'path': result['path']}))
"@

$output = python -c $py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$parsed = $output | ConvertFrom-Json
Write-Host "Backup created: $($parsed.backup_id)" -ForegroundColor Green
Write-Host "Path: $($parsed.path)"
exit 0
