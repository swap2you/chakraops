#!/usr/bin/env bash
# R25.0: Backup ./out to ./backups/out_<timestamp>.tar.gz; retain last BACKUP_KEEP_N (default 14).
# Run from repository root: ./scripts/backup_out.sh

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
OUT_DIR="${OUT_DIR:-./out}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_N="${BACKUP_KEEP_N:-14}"
TIMESTAMP=$(date -u +%Y%m%d_%H%M%S)
ARCHIVE="$BACKUP_DIR/out_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"
if [ ! -d "$OUT_DIR" ]; then
  echo "out dir not found: $OUT_DIR" >&2
  exit 1
fi
tar -czf "$ARCHIVE" -C "$REPO_ROOT" out
echo "Created $ARCHIVE"

# Keep only last KEEP_N archives (by mtime)
count=0
for f in $(ls -t "$BACKUP_DIR"/out_*.tar.gz 2>/dev/null); do
  count=$((count + 1))
  if [ "$count" -gt "$KEEP_N" ]; then
    rm -f "$f"
  fi
done
echo "Retention: kept last $KEEP_N archives in $BACKUP_DIR"
