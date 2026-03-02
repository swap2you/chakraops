#!/usr/bin/env bash
# R26.6: Restore a backup tar.gz into DATA_DIR (default ./data).
# Usage: ./scripts/restore_data.sh [--force] <path-to-backup.tar.gz>
# Safety: backup must exist; DATA_DIR must be a directory; --force allows overwriting non-empty dir.
# Stop containers/app before restore.

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
DATA_DIR="${DATA_DIR:-./data}"
FORCE=0
BACKUP_FILE=""

for arg in "$@"; do
  if [ "$arg" = "--force" ]; then
    FORCE=1
  else
    BACKUP_FILE="$arg"
  fi
done

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: $0 [--force] <path-to-backup.tar.gz>" >&2
  echo "Example: $0 ./backups/data_20260227_120000.tar.gz" >&2
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Backup file not found: $BACKUP_FILE" >&2
  exit 1
fi

if [ -e "$DATA_DIR" ] && [ ! -d "$DATA_DIR" ]; then
  echo "Refusing: DATA_DIR is not a directory: $DATA_DIR" >&2
  exit 1
fi

if [ -d "$DATA_DIR" ] && [ -n "$(ls -A "$DATA_DIR" 2>/dev/null)" ] && [ "$FORCE" -eq 0 ]; then
  echo "Refusing: DATA_DIR is non-empty. Use --force to overwrite." >&2
  exit 1
fi

echo "Before restore: stop any running app or containers using $DATA_DIR."
echo "Then press Enter to continue, or Ctrl+C to abort."
read -r _

mkdir -p "$DATA_DIR"
# Extract archive (archive contains a single top-level 'data' or similar)
tar -xzf "$BACKUP_FILE" -C "$REPO_ROOT"
echo "Restored $BACKUP_FILE into $DATA_DIR (contents extracted to repo root)."
echo "Restart app/containers when ready."
