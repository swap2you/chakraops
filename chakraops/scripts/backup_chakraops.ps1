# ChakraOps backup — R35.0
$ErrorActionPreference = "Stop"
$Backend = "C:\Development\Workspace\ChakraOps-dev\chakraops\chakraops"
Set-Location $Backend
python -c "from app.core.operations.backup_service import create_backup, verify_backup; c=create_backup(label='manual'); v=verify_backup(c['backup_id']); print(c['backup_id'], v['ok'])"
