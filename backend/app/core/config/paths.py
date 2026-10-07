# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Path configuration constants for ChakraOps.

This module provides a single source of truth for file system paths,
especially the database path.
"""

from __future__ import annotations

import logging
from pathlib import Path

# Base directory: chakraops/ (repo root)
# This file is at: chakraops/app/core/config/paths.py
# So BASE_DIR = Path(__file__).resolve().parents[3] = chakraops/
BASE_DIR = Path(__file__).resolve().parents[3]

# Database path: app/data/chakraops.db (relative to repo root)
DB_PATH = BASE_DIR / "app" / "data" / "chakraops.db"

# Ensure data directory exists
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Log once at module import
logger = logging.getLogger(__name__)

# Step 5: Detect duplicate DB files and warn
_data_dir = DB_PATH.parent
if _data_dir.exists():
    db_files = list(_data_dir.glob("*.db"))
    if len(db_files) > 1:
        logger.warning(
            f"[CONFIG] Multiple DB files found in {_data_dir}: {[f.name for f in db_files]}. "
            f"Using canonical: {DB_PATH.name}"
        )

logger.info(f"[CONFIG] Using DB_PATH={DB_PATH.absolute()}")

__all__ = ["BASE_DIR", "DB_PATH"]
