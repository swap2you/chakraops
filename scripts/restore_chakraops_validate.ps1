# ChakraOps — restore to temp for validation only (R35.0)
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupId
)
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout

$escaped = $BackupId.Replace("'", "''")
python -c @"
import json
from app.core.operations.backup_service import restore_to_temp
result = restore_to_temp('$escaped')
print(json.dumps(result, indent=2))
if not result.get('ok'):
    raise SystemExit(1)
"@
exit $LASTEXITCODE
