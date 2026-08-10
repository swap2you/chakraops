# R57 — Optional local production Compose smoke (api + frontend).
# Requires Docker Desktop / Compose. Does not enable scheduler or broker writes.
# Usage (repo root):
#   .\scripts\smoke_prod_compose.ps1
#   .\scripts\smoke_prod_compose.ps1 -SkipBuild
#   .\scripts\smoke_prod_compose.ps1 -Down

[CmdletBinding()]
param(
  [switch]$SkipBuild,
  [switch]$Down,
  [int]$TimeoutSec = 120
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $RepoRoot "deploy\docker-compose.prod.yml"
$EnvExample = Join-Path $RepoRoot "deploy\.env.prod.example"
$EnvFile = Join-Path $RepoRoot "deploy\.env.prod"

if (-not (Test-Path $ComposeFile)) {
  Write-Error "Missing compose file: $ComposeFile"
}

if (-not (Test-Path $EnvFile)) {
  Write-Host "Creating deploy\.env.prod from example (local only; do not commit)..."
  Copy-Item -Path $EnvExample -Destination $EnvFile
}

Push-Location $RepoRoot
try {
  if ($Down) {
    docker compose -f $ComposeFile --env-file $EnvFile down --remove-orphans
    Write-Host "Compose down complete."
    exit 0
  }

  $upArgs = @("compose", "-f", $ComposeFile, "--env-file", $EnvFile, "up", "-d")
  if (-not $SkipBuild) {
    $upArgs += "--build"
  }
  # Core services only (no postgres/monitor profiles) for fast smoke.
  & docker @upArgs "api" "frontend"
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed with exit $LASTEXITCODE"
  }

  $healthUrl = "http://127.0.0.1:18873/api/healthz"
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $ok = $false
  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
      if ($resp.StatusCode -eq 200) {
        Write-Host "healthz OK: $healthUrl"
        Write-Host $resp.Content
        $ok = $true
        break
      }
    } catch {
      Start-Sleep -Seconds 3
    }
  }

  if (-not $ok) {
    Write-Host "healthz FAILED within ${TimeoutSec}s: $healthUrl" -ForegroundColor Red
    docker compose -f $ComposeFile --env-file $EnvFile logs --tail 80 api frontend
    exit 1
  }

  Write-Host "R57 smoke passed (scheduler must remain disabled in deploy/.env.prod)."
  exit 0
} finally {
  Pop-Location
}
