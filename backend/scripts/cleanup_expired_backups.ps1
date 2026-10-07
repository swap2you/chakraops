# ChakraOps cleanup expired backups — R35.0
$Backend = "$PSScriptRoot\.."
Set-Location $Backend
python -c "from app.core.operations.backup_service import cleanup_expired_backups; import json; print(json.dumps(cleanup_expired_backups()))"
