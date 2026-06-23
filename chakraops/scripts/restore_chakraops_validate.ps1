# ChakraOps restore validation (temp path only) — R35.0
param([Parameter(Mandatory=$true)][string]$BackupId)
$Backend = "C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops"
Set-Location $Backend
python -c "from app.core.operations.backup_service import restore_to_temp; import json; print(json.dumps(restore_to_temp('$BackupId')))"
