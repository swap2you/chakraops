# ChakraOps Windows startup — R35.0
# Repository: C:\Development\Workspace\ChakraOps-dev\chakraops
$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Development\Workspace\ChakraOps-dev\chakraops"
$Backend = Join-Path $RepoRoot "chakraops"
$Frontend = Join-Path $RepoRoot "frontend"

Write-Host "=== ChakraOps Startup ===" -ForegroundColor Cyan
if (-not (Test-Path $RepoRoot)) { throw "Repository not found: $RepoRoot" }
Set-Location $RepoRoot

Write-Host "Checking Python..."
python --version | Out-Null

Write-Host "Checking Node..."
node --version | Out-Null

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  Push-Location $Frontend; npm install; Pop-Location
}

$envFile = Join-Path $Backend ".env"
if (Test-Path $envFile) {
  Write-Host "Loading .env (values not displayed)"
} else {
  Write-Host "WARNING: .env not found at $envFile" -ForegroundColor Yellow
}

$env:CHAKRAOPS_SCHEDULER_ENABLED = "false"
Write-Host "Scheduler: DISABLED by default (set CHAKRAOPS_SCHEDULER_ENABLED=true to enable)"

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Backend'; python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8000"

Start-Sleep -Seconds 2
Write-Host "Starting frontend on http://127.0.0.1:5173 ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$Frontend'; npm run dev -- --host 127.0.0.1 --port 5173"

Write-Host "Health check..."
Start-Sleep -Seconds 3
try {
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/operations/status" -TimeoutSec 10
  Write-Host "Backend OK — jobs registered:" ($health.scheduler.jobs.Count)
} catch {
  Write-Host "Backend health pending — check backend window" -ForegroundColor Yellow
}

Write-Host "URLs:"
Write-Host "  Backend:  http://127.0.0.1:8000"
Write-Host "  Frontend: http://127.0.0.1:5173"
Write-Host "  Ops API:  http://127.0.0.1:8000/api/operations/status"
