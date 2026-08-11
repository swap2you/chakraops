# Operator production deploy (VPS)

Requires owner-provisioned Ubuntu VPS + secrets under /opt/chakraops/secrets/.

Never paste tokens into chat/Git.

```powershell
# On operator machine with SSH access configured:
# 1) rsync/git pull checkout to /opt/chakraops/app
# 2) Ensure secrets exist:
#    /opt/chakraops/secrets/env.prod
#    /opt/chakraops/secrets/robinhood_mcp_token
#    /opt/chakraops/secrets/cloudflare_tunnel_token
#    /opt/chakraops/secrets/postgres_password (mirrored into env.prod)

param(
  [string]$AppDir = "/opt/chakraops/app",
  [string]$EnvFile = "/opt/chakraops/secrets/env.prod"
)

$ErrorActionPreference = "Stop"
Set-Location $AppDir

Write-Host "Running Alembic migrations..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile run --rm api `
  python -m alembic upgrade head

Write-Host "Building/up production stack..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile up -d --build

Write-Host "Health check (internal)..."
docker compose -f deploy/docker-compose.prod.yml --env-file $EnvFile exec -T api `
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/healthz').read().decode())"

Write-Host "Done. Remote acceptance via https://chakraops.cloud after Cloudflare Access/Tunnel."
```
