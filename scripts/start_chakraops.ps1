# ChakraOps Windows startup — R35.0 remediation
. "$PSScriptRoot\chakraops_common.ps1"
Initialize-ChakraOpsCheckout

Write-Host "=== ChakraOps Startup ===" -ForegroundColor Cyan

Write-Host "Checking Python..."
python --version | Out-Null

Write-Host "Checking Node..."
node --version | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $script:ChakraOpsFrontendRoot "node_modules"))) {
    throw "Frontend dependencies missing. Run: cd $($script:ChakraOpsFrontendRoot); npm install"
}

function Test-PortFree([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    if ($conn) { throw "Port $Port already in use (PID $($conn.OwningProcess))" }
}

Test-PortFree $script:ChakraOpsBackendPort
Test-PortFree $script:ChakraOpsFrontendPort

$envFile = Join-Path $script:ChakraOpsBackendRoot ".env"
if (Test-Path -LiteralPath $envFile) {
    Write-Host "Loading .env (values not displayed)"
} else {
    Write-Host "WARNING: .env not found at $envFile" -ForegroundColor Yellow
}

$env:CHAKRAOPS_SCHEDULER_ENABLED = "false"
$env:CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED = "false"
Write-Host "Scheduler: DISABLED by default (master + legacy)"

$backendProc = Start-Process python -ArgumentList "-m", "uvicorn", "app.api.server:app", "--host", "127.0.0.1", "--port", "$($script:ChakraOpsBackendPort)" -WorkingDirectory $script:ChakraOpsBackendRoot -PassThru -WindowStyle Normal
Start-Sleep -Seconds 2
$frontendProc = Start-Process npm -ArgumentList "run", "dev" -WorkingDirectory $script:ChakraOpsFrontendRoot -PassThru -WindowStyle Normal
Start-Sleep -Seconds 3
$frontendListener = Get-NetTCPConnection -LocalPort $script:ChakraOpsFrontendPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
$frontendPid = if ($frontendListener) { [int]$frontendListener.OwningProcess } else { [int]$frontendProc.Id }

python -c "from app.core.operations.process_ownership import write_record; from app.core.chakraops_ports import BACKEND_PORT, FRONTEND_PORT; write_record(backend_pid=$($backendProc.Id), frontend_pid=$frontendPid, repo_root=r'$($script:ChakraOpsRepoRoot)', backend_cmd='uvicorn app.api.server:app', frontend_cmd='npm run dev', backend_port=BACKEND_PORT, frontend_port=FRONTEND_PORT)" | Out-Null

Write-Host "Backend PID: $($backendProc.Id)  Frontend PID: $frontendPid"
Write-Host "URLs: $($script:ChakraOpsBackendUrl)  $($script:ChakraOpsFrontendUrl)"
