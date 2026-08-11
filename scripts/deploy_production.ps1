# Operator production deploy for https://chakraops.cloud
# Run on the VPS (or via SSH). Secrets stay under /opt/chakraops/secrets/ — never in Git.
# Prerequisites: owner-provisioned Ubuntu VPS, Docker Compose, Cloudflare tunnel token file.

param(
  [string]$AppDir = "/opt/chakraops/app",
  [string]$EnvFile = "/opt/chakraops/secrets/env.prod"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $AppDir)) {
  throw "AppDir not found: $AppDir"
}
if (-not (Test-Path $EnvFile)) {
  throw "Env file not found: $EnvFile (copy from deploy/.env.prod.example; keep on server only)"
}

Set-Location $AppDir

Write-Host "Running Alembic migrations..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile run --rm api `
  python -m alembic upgrade head

Write-Host "Building/up production stack (postgres mandatory, no public api/postgres ports)..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile up -d --build

Write-Host "Health check (internal api)..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile exec -T api `
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/healthz').read().decode())"

Write-Host "Done. Remote acceptance via https://chakraops.cloud after Cloudflare Access/Tunnel (see OWNER_ACTION_STATE)."
