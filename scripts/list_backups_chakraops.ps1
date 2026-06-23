# ChakraOps — list backups (R35.0)
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
from app.core.operations.backup_service import list_backups
print(json.dumps(list_backups(), indent=2))
"@

python -c $py
exit $LASTEXITCODE
