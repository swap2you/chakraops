# ChakraOps list backups — R35.0
$Backend = "$PSScriptRoot\.."
Set-Location $Backend
python -c "from app.core.operations.backup_service import list_backups; import json; print(json.dumps(list_backups(), indent=2))"
