#!/usr/bin/env bash
# R26.7: Restore drill + smoke test — prove backups are usable.
# Finds latest out_*.tar.gz and data_*.tar.gz in ./backups, extracts to temp,
# runs backend with OUT_DIR/DATA_DIR override on port 8010, hits healthz + system-health + reports, then cleans up.
# Usage: ./scripts/restore_drill.sh [--keep]
# --keep: do not remove temp dir or kill backend (for inspection).
# Requires: bash, curl, mktemp. Run from repository root (parent of scripts/).

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
APP_ROOT="$REPO_ROOT/chakraops"
PORT=8010
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

LATEST_OUT=""
LATEST_DATA=""
for f in $(ls -t "$BACKUP_DIR"/out_*.tar.gz 2>/dev/null); do
  LATEST_OUT="$f"
  break
done
for f in $(ls -t "$BACKUP_DIR"/data_*.tar.gz 2>/dev/null); do
  LATEST_DATA="$f"
  break
done
if [ -z "$LATEST_OUT" ] || [ -z "$LATEST_DATA" ]; then
  echo "Need both out_*.tar.gz and data_*.tar.gz in $BACKUP_DIR" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d 2>/dev/null || echo "$REPO_ROOT/.restore_drill_$$")"
mkdir -p "$TEMP_DIR"
trap '([ "$KEEP" -eq 0 ] && rm -rf "$TEMP_DIR") 2>/dev/null || true' EXIT

echo "Extracting backups into $TEMP_DIR"
tar -xzf "$LATEST_OUT" -C "$TEMP_DIR"
tar -xzf "$LATEST_DATA" -C "$TEMP_DIR"

OUT_DIR="$TEMP_DIR/out"
DATA_DIR="$TEMP_DIR/data"
[ ! -d "$OUT_DIR" ] && echo "Archive did not create out/" >&2 && exit 1
[ ! -d "$DATA_DIR" ] && echo "Archive did not create data/" >&2 && exit 1

export OUT_DIR
export DATA_DIR
export PYTHONPATH="$APP_ROOT"

echo "Starting backend on port $PORT (OUT_DIR=$OUT_DIR DATA_DIR=$DATA_DIR)"
cd "$APP_ROOT"
python -m uvicorn app.api.server:app --host 127.0.0.1 --port "$PORT" &
UVICORN_PID=$!
if [ "$KEEP" -eq 0 ]; then
  trap 'kill $UVICORN_PID 2>/dev/null; wait $UVICORN_PID 2>/dev/null; ([ "$KEEP" -eq 0 ] && rm -rf "$TEMP_DIR") 2>/dev/null || true' EXIT
fi

echo "Waiting for /api/healthz..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -s -f "http://127.0.0.1:$PORT/api/healthz" >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 10 ] && echo "Healthz timeout" >&2 && kill $UVICORN_PID 2>/dev/null && exit 1
  sleep 1
done

MONTH="$(date +%Y-%m)"
echo "Smoke: GET /api/healthz"
curl -s -S "http://127.0.0.1:$PORT/api/healthz" | head -c 200
echo ""
echo "Smoke: GET /api/ui/system-health (no UI key required for health)"
curl -s -S -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/ui/system-health"
echo ""
echo "Smoke: GET /api/ui/reports/monthly?month=$MONTH (may 404 without key)"
curl -s -S -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/api/ui/reports/monthly?month=$MONTH"
echo ""
echo "Smoke: POST /api/ui/reports/monthly/close?month=$MONTH (may 401 without key; creates pack under DATA_DIR)"
curl -s -S -o /dev/null -w "%{http_code}" -X POST "http://127.0.0.1:$PORT/api/ui/reports/monthly/close?month=$MONTH"
echo ""

echo "--- DRILL OK ---"
echo "Temp: $TEMP_DIR"
echo "OUT_DIR=$OUT_DIR DATA_DIR=$DATA_DIR"
if [ -d "$DATA_DIR/reports" ]; then
  echo "data/reports: $(ls "$DATA_DIR/reports" 2>/dev/null | tr '\n' ' ')"
fi

if [ "$KEEP" -eq 0 ]; then
  kill $UVICORN_PID 2>/dev/null || true
  wait $UVICORN_PID 2>/dev/null || true
  echo "Backend stopped; temp dir removed."
else
  echo "Backend PID $UVICORN_PID; temp kept at $TEMP_DIR (--keep)."
fi
