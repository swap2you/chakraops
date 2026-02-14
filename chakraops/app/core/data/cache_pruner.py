# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.9: Cache pruning — prevent unbounded growth.

Remove files older than max_age_days; if still above max_files, delete oldest.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def prune_cache(
    cache_dir: Path,
    max_age_days: int = 7,
    max_files: int = 20000,
) -> Dict[str, Any]:
    """
    Remove cache files older than max_age_days.
    If remaining count > max_files, delete oldest until within limit.
    Returns {"deleted": int, "remaining": int}.
    """
    if not cache_dir.exists():
        return {"deleted": 0, "remaining": 0}
    cutoff = time.time() - (max_age_days * 86400)
    deleted = 0
    files_with_mtime: list[tuple[Path, float]] = []
    try:
        for p in cache_dir.glob("*.json"):
            try:
                mtime = p.stat().st_mtime
                if mtime < cutoff:
                    p.unlink()
                    deleted += 1
                else:
                    files_with_mtime.append((p, mtime))
            except OSError as e:
                logger.debug("[CACHE_PRUNE] skip %s: %s", p.name, e)
        remaining = len(files_with_mtime)
        if remaining > max_files:
            files_with_mtime.sort(key=lambda x: x[1])
            to_remove = remaining - max_files
            for p, _ in files_with_mtime[:to_remove]:
                try:
                    p.unlink()
                    deleted += 1
                    remaining -= 1
                except OSError as e:
                    logger.debug("[CACHE_PRUNE] remove failed %s: %s", p.name, e)
        return {"deleted": deleted, "remaining": remaining}
    except Exception as e:
        logger.warning("[CACHE_PRUNE] Failed: %s", e)
        return {"deleted": deleted, "remaining": -1}
