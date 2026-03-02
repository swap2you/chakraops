#!/usr/bin/env bash
# R26.6: Keep last REPORTS_KEEP_N months (default 24) under data/reports; delete older month folders.
# Usage: ./scripts/cleanup_reports.sh [--dry-run]
# Run from repository root (parent of scripts/).

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
REPORTS_DIR="${REPORTS_DIR:-./data/reports}"
KEEP_N="${REPORTS_KEEP_N:-24}"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

if [ ! -d "$REPORTS_DIR" ]; then
  echo "Reports dir not found: $REPORTS_DIR" >&2
  exit 1
fi

# List YYYY-MM dirs, sort descending (newest first), keep first KEEP_N, delete the rest
# Only consider dirs matching YYYY-MM (4 digits, dash, 2 digits)
count=0
deleted=0
for d in $(find "$REPORTS_DIR" -maxdepth 1 -type d -name '[0-9][0-9][0-9][0-9]-[0-9][0-9]' 2>/dev/null | sort -r); do
  count=$((count + 1))
  if [ "$count" -gt "$KEEP_N" ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "[dry-run] would remove: $d"
    else
      rm -rf "$d"
      echo "Removed: $d"
    fi
    deleted=$((deleted + 1))
  fi
done
if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry-run: would remove $deleted month(s); keeping last $KEEP_N."
else
  echo "Retention: kept last $KEEP_N month(s) in $REPORTS_DIR; removed $deleted."
fi
