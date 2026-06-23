# ChakraOps health check — R35.0
$ErrorActionPreference = "Stop"
try {
  $ops = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/operations/status" -TimeoutSec 5
  Write-Host "Backend: OK"
  Write-Host "Scheduler master:" $ops.scheduler.master_enabled
  Write-Host "ORATS token present:" $ops.orats_token_present
  exit 0
} catch {
  Write-Host "Backend: UNREACHABLE" -ForegroundColor Red
  exit 1
}
