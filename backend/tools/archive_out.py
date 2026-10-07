#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Archive old evaluation artifacts from out/evaluations/ to out/archive/.

Keeps the last --keep-days days of run JSONs (and their _data_completeness.json
sidecars) in out/evaluations/. Older files are moved into out/archive/ in
date-based subfolders (YYYY-MM) so they remain findable. latest.json and the
run it points to are never archived.

Usage:
  cd chakraops
  python tools/archive_out.py --keep-days 30
  python tools/archive_out.py --keep-days 14 --dry-run

Non-destructive: files are moved, not deleted. Run periodically (e.g. weekly)
or via cron.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_KEEP_DAYS = 30
EVAL_DIR_NAME = "evaluations"
ARCHIVE_DIR_NAME = "archive"
LATEST_FILENAME = "latest.json"


def _find_out_dir() -> Path:
    """Resolve out/ relative to chakraops (parent of tools/)."""
    script_dir = Path(__file__).resolve().parent
    # tools/ is under chakraops/
    chakraops_root = script_dir.parent
    return chakraops_root / "out"


def _get_latest_run_id(eval_dir: Path) -> str | None:
    """Read latest.json and return the run_id it points to, or None."""
    latest_path = eval_dir / LATEST_FILENAME
    if not latest_path.exists():
        return None
    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
        return data.get("run_id") or None
    except Exception:
        return None


def _run_id_from_filename(name: str) -> str | None:
    """Return run_id for eval_*.json or eval_*_data_completeness.json, else None."""
    if name == LATEST_FILENAME:
        return None
    if name.endswith("_data_completeness.json"):
        base = name.replace("_data_completeness.json", "")
        return base if base.startswith("eval_") else None
    if name.startswith("eval_") and name.endswith(".json"):
        return name[:-5]  # strip .json
    return None


def _file_age_days(path: Path) -> float:
    """Age of file in days (from mtime)."""
    mtime = path.stat().st_mtime
    now = datetime.now(timezone.utc).timestamp()
    return (now - mtime) / 86400.0


def archive_out(
    out_dir: Path,
    keep_days: int = DEFAULT_KEEP_DAYS,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Move evaluation files older than keep_days into out/archive/.
    Returns (count_archived, count_skipped).
    """
    eval_dir = out_dir / EVAL_DIR_NAME
    archive_base = out_dir / ARCHIVE_DIR_NAME
    if not eval_dir.exists():
        logger.warning("Evaluations dir does not exist: %s", eval_dir)
        return 0, 0

    latest_run_id = _get_latest_run_id(eval_dir)
    cutoff_days = float(keep_days)
    archived = 0
    skipped = 0

    # Collect run files (eval_*.json and *_data_completeness.json) and group by run_id
    run_files: dict[str, list[Path]] = {}
    for f in eval_dir.iterdir():
        if not f.is_file():
            continue
        rid = _run_id_from_filename(f.name)
        if rid is None:
            continue
        run_files.setdefault(rid, []).append(f)

    for run_id, files in run_files.items():
        if run_id == latest_run_id:
            skipped += len(files)
            continue
        # Use oldest mtime among the group as the "run age"
        age_days = min(_file_age_days(p) for p in files)
        if age_days <= cutoff_days:
            skipped += len(files)
            continue
        # Archive all files for this run_id into a date-based subfolder
        first_path = files[0]
        mtime = first_path.stat().st_mtime
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        subdir = archive_base / dt.strftime("%Y-%m")
        if not dry_run:
            subdir.mkdir(parents=True, exist_ok=True)
        for p in files:
            dest = subdir / p.name
            if dry_run:
                logger.info("Would move %s -> %s", p, dest)
            else:
                shutil.move(str(p), str(dest))
                logger.info("Moved %s -> %s", p.name, dest)
            archived += 1

    return archived, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Archive old evaluation run files from out/evaluations/ to out/archive/."
    )
    parser.add_argument(
        "--keep-days",
        type=int,
        default=DEFAULT_KEEP_DAYS,
        help="Keep runs from the last N days in out/evaluations/ (default: %s)" % DEFAULT_KEEP_DAYS,
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Override out/ directory (default: chakraops/out)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only log what would be moved; do not move files.",
    )
    args = parser.parse_args()
    out_dir = args.out_dir or _find_out_dir()
    if not out_dir.is_absolute():
        out_dir = out_dir.resolve()
    archived, skipped = archive_out(
        out_dir,
        keep_days=args.keep_days,
        dry_run=args.dry_run,
    )
    logger.info("Done: %s archived, %s skipped (keep-days=%s)", archived, skipped, args.keep_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
