# ChakraOps Windows startup — R35.0 remediation
# Repository: C:\Development\Workspace\ChakraOps-dev\chakraops
$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
$Backend = Join-Path $RepoRoot "chakraops"
$Frontend = Join-Path $RepoRoot "frontend"
$StaleRoot = "C:\Development\Workspace\ChakraOps"
$OwnershipScript = "from app.core.operations.process_ownership import validate_repo_root, write_record; validate_repo_root(r'$RepoRoot')"

Write-Host "=== ChakraOps Startup ===" -ForegroundColor Cyan
if (-not (Test-Path $RepoRoot)) { throw "Repository not found: $RepoRoot" }
if ((Get-Location).Path -like "$StaleRoot*") {
  throw "Stale checkout detected. Use $RepoRoot"
}
Set-Location $Backend
python -c $OwnershipScript | Out-Null

Write-Host "Checking Python..."
python --version | Out-Null

Write-Host "Checking Node..."
node --version | Out-Null

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
  throw "Frontend dependencies missing. Run: cd $Frontend; npm install"
}

function Test-PortFree([int]$Port) {
  $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
  if ($conn) { throw "Port $Port already in use (PID $($conn.OwningProcess))" }
}

Test-PortFree 8000
Test-PortFree 5173

$envFile = Join-Path $Backend ".env"
if (Test-Path $envFile) {
  Write-Host "Loading .env (values not displayed)"
} else {
  Write-Host "WARNING: .env not found at $envFile" -ForegroundColor Yellow
}

$env:CHAKRAOPS_SCHEDULER_ENABLED = "false"
Write-Host "Scheduler: DISABLED by default"

$backendProc = Start-Process python -ArgumentList "-m", "uvicorn", "app.api.server:app", "--host", "127.0.0.1", "--port", "8000" -WorkingDirectory $Backend -PassThru -WindowStyle Normal
Start-Sleep -Seconds 2
$frontendProc = Start-Process npm -ArgumentList "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173" -WorkingDirectory $Frontend -PassThru -WindowStyle Normal

python -c "from app.core.operations.process_ownership import write_record; write_record(backend_pid=$($backendProc.Id), frontend_pid=$($frontendProc.Id), repo_root=r'$RepoRoot', backend_cmd='uvicorn app.api.server:app', frontend_cmd='npm run dev')" | Out-Null

Write-Host "Backend PID: $($backendProc.Id)  Frontend PID: $($frontendProc.Id)"
Write-Host "URLs: http://127.0.0.1:8000  http://127.0.0.1:5173"
