# ChakraOps — create backup (R35.0)
param(
    [string]$Label = "manual"
)
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout

$escapedLabel = $Label.Replace("'", "''")
$resultJson = python -c "import json; from app.core.operations.backup_service import create_backup; r=create_backup(label='$escapedLabel'); print(json.dumps({'backup_id': r['backup_id'], 'path': r['path']}))"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$parsed = $resultJson | ConvertFrom-Json
Write-Host "Backup created: $($parsed.backup_id)" -ForegroundColor Green
Write-Host "Path: $($parsed.path)"
exit 0
