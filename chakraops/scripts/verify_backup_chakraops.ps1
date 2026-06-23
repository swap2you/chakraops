# ChakraOps verify backup — R35.0
param([Parameter(Mandatory=$true)][string]$BackupId)
$Backend = "C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops"
Set-Location $Backend
python -c "from app.core.operations.backup_service import verify_backup; import json; print(json.dumps(verify_backup('$BackupId')))"
