# ChakraOps Windows startup - R35.0 + R70-DEF-072 (reliable npm.cmd + listen wait)
. "$PSScriptRoot\chakraops_common.ps1"
. "$PSScriptRoot\chakraops_startup.ps1"
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
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
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

$npmLauncher = Resolve-ChakraOpsNpmLauncher
Write-Host "npm launcher: $npmLauncher"

$backendProc = $null
$frontendProc = $null
$startupOk = $false
$healthRegex = '"ok"\s*:\s*true|"status"\s*:\s*"ok"'

try {
    $backendProc = Start-Process -FilePath "python" -ArgumentList @(
        "-m", "uvicorn", "app.api.server:app",
        "--host", "127.0.0.1",
        "--port", "$($script:ChakraOpsBackendPort)"
    ) -WorkingDirectory $script:ChakraOpsBackendRoot -PassThru -WindowStyle Normal

    # Launch via cmd.exe /c so .cmd files work reliably under NVM.
    # Never invoke the extensionless npm shim via Start-Process.
    $frontendCmd = "`"$npmLauncher`" run dev -- --host 127.0.0.1 --port $($script:ChakraOpsFrontendPort)"
    $frontendProc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $frontendCmd) `
        -WorkingDirectory $script:ChakraOpsFrontendRoot -PassThru -WindowStyle Normal

    Write-Host "Waiting for backend LISTEN on $($script:ChakraOpsBackendPort)..."
    $backendListenPid = Wait-ChakraOpsPortListen -Port $script:ChakraOpsBackendPort -Label "Backend" -TimeoutSec 90

    Write-Host "Waiting for frontend LISTEN on $($script:ChakraOpsFrontendPort)..."
    $frontendListenPid = Wait-ChakraOpsPortListen -Port $script:ChakraOpsFrontendPort -Label "Frontend" -TimeoutSec 120

    Write-Host "Waiting for backend healthz..."
    Wait-ChakraOpsHttpOk -Url ($script:ChakraOpsBackendUrl + "/api/healthz") -Label "Backend healthz" `
        -TimeoutSec 60 -ContentRegex $healthRegex

    Write-Host "Waiting for frontend HTTP..."
    Wait-ChakraOpsHttpOk -Url $script:ChakraOpsFrontendUrl -Label "Frontend HTTP" -TimeoutSec 60

    Write-Host "Waiting for frontend /api proxy to backend..."
    Wait-ChakraOpsHttpOk -Url ($script:ChakraOpsFrontendUrl + "/api/healthz") -Label "Frontend /api proxy" `
        -TimeoutSec 60 -ContentRegex $healthRegex

    # Ownership uses LISTEN PIDs (not the npm/cmd parent PID).
    python -c "from app.core.operations.process_ownership import write_record; from app.core.chakraops_ports import BACKEND_PORT, FRONTEND_PORT; write_record(backend_pid=$backendListenPid, frontend_pid=$frontendListenPid, repo_root=r'$($script:ChakraOpsRepoRoot)', backend_cmd='uvicorn app.api.server:app', frontend_cmd='npm run dev', backend_port=BACKEND_PORT, frontend_port=FRONTEND_PORT)" | Out-Null

    $startupOk = $true
    Write-Host "Backend PID: $backendListenPid (spawn=$($backendProc.Id))  Frontend PID: $frontendListenPid (spawn=$($frontendProc.Id))"
    Write-Host "URLs: $($script:ChakraOpsBackendUrl)  $($script:ChakraOpsFrontendUrl)"
    Write-Host "Startup OK - ownership recorded." -ForegroundColor Green
}
catch {
    Write-Host ("STARTUP FAILED: " + $_.Exception.Message) -ForegroundColor Red
    Stop-ChakraOpsStartedProcesses -BackendProc $backendProc -FrontendProc $frontendProc `
        -BackendPort $script:ChakraOpsBackendPort -FrontendPort $script:ChakraOpsFrontendPort
    Write-Host "Partial processes stopped. Ownership record NOT written." -ForegroundColor Yellow
    exit 1
}

if (-not $startupOk) {
    exit 1
}
