# ChakraOps health check — R35.0
. "$PSScriptRoot\chakraops_ports.ps1"
$ErrorActionPreference = "Stop"
try {
  $ops = Invoke-RestMethod -Uri "$($script:ChakraOpsBackendUrl)/api/operations/status" -TimeoutSec 5
  Write-Host "Backend: OK ($($script:ChakraOpsBackendUrl))"
  Write-Host "Scheduler master:" $ops.scheduler.master_enabled
  Write-Host "ORATS token present:" $ops.orats_token_present
  exit 0
} catch {
  Write-Host "Backend: UNREACHABLE at $($script:ChakraOpsBackendUrl)" -ForegroundColor Red
  exit 1
}
