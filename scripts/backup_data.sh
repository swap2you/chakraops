#!/usr/bin/env bash
# R26.6: Backup ./data to ./backups/data_<timestamp>.tar.gz; retain last BACKUP_KEEP_N (default 14).
# Run from repository root (parent of scripts/): ./scripts/backup_data.sh
# Env: DATA_DIR=./data, BACKUP_DIR=./backups, BACKUP_KEEP_N=14

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
DATA_DIR="${DATA_DIR:-./data}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_N="${BACKUP_KEEP_N:-14}"
TIMESTAMP="$(date -u +%Y%m%d_%H%M%S)"
ARCHIVE="$BACKUP_DIR/data_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"
if [ ! -d "$DATA_DIR" ]; then
  echo "data dir not found: $DATA_DIR" >&2
  exit 1
fi

# Path relative to REPO_ROOT for tar (strip leading ./)
TAR_MEMBER="${DATA_DIR#./}"
[ -z "$TAR_MEMBER" ] && TAR_MEMBER="data"
# Exclude ephemeral/cache patterns (deny list)
tar -czf "$ARCHIVE" -C "$REPO_ROOT" \
  --exclude='*.tmp' \
  --exclude='*.cache' \
  --exclude='.cache' \
  "$TAR_MEMBER"
echo "Created $ARCHIVE"

# Keep only last KEEP_N archives (by mtime)
count=0
for f in $(ls -t "$BACKUP_DIR"/data_*.tar.gz 2>/dev/null); do
  count=$((count + 1))
  if [ "$count" -gt "$KEEP_N" ]; then
    rm -f "$f"
  fi
done
echo "Retention: kept last $KEEP_N archives in $BACKUP_DIR"
