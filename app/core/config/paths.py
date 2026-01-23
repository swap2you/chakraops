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
logger.info(f"[CONFIG] Using DB_PATH={DB_PATH.absolute()}")

__all__ = ["BASE_DIR", "DB_PATH"]
