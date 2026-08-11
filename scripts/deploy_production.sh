#!/usr/bin/env bash
# Operator production deploy for https://chakraops.cloud
# Run on the VPS. Secrets stay under /opt/chakraops/secrets/ — never in Git.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/chakraops/app}"
ENV_FILE="${ENV_FILE:-/opt/chakraops/secrets/env.prod}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "AppDir not found: $APP_DIR" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE (copy from deploy/.env.prod.example; keep on server only)" >&2
  exit 1
fi

cd "$APP_DIR"

echo "Running Alembic migrations..."
docker compose -f deploy/docker-compose.prod.yml --env-file "$ENV_FILE" run --rm api \
  python -m alembic upgrade head

echo "Building/up production stack (postgres mandatory, no public api/postgres ports)..."
docker compose -f deploy/docker-compose.prod.yml --env-file "$ENV_FILE" up -d --build

echo "Health check (internal api)..."
docker compose -f deploy/docker-compose.prod.yml --env-file "$ENV_FILE" exec -T api \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/healthz').read().decode())"

echo "Done. Remote acceptance via https://chakraops.cloud after Cloudflare Access/Tunnel (see OWNER_ACTION_STATE)."
