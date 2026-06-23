# ChakraOps — list backups (R35.0)
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout
python -c "import json; from app.core.operations.backup_service import list_backups; print(json.dumps(list_backups(), indent=2))"
exit $LASTEXITCODE
