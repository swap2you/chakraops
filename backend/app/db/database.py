# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Database operations for ChakraOps."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.utils import safe_json
from app.core.config.paths import DB_PATH


def get_db_path() -> Path:
    """Get path to SQLite database.
    
    Returns the canonical DB_PATH from app.core.config.paths.
    This ensures all modules use the same database file.
    """
    return DB_PATH


def init_db() -> None:
    """Initialize database with required tables."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Create regime_snapshots table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regime_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            regime TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            details TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Create alerts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            level TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_created_at ON regime_snapshots(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC)")

    conn.commit()
    conn.close()
    
    # Initialize Phase 1A persistence tables
    from app.core.persistence import init_persistence_db
    init_persistence_db()


def log_regime_snapshot(regime: str, confidence: int, details: Dict[str, Any]) -> None:
    """Log regime snapshot to database."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Convert numpy/pandas types to native Python types before JSON serialization
    details_safe = safe_json(details)
    
    cursor.execute("""
        INSERT INTO regime_snapshots (regime, confidence, details, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        regime,
        confidence,
        json.dumps(details_safe),
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()


def log_csp_candidates(candidates: List[Dict[str, Any]]) -> None:
    """Legacy function - DEPRECATED.
    
    This function is kept for backward compatibility but does nothing.
    CSP candidates are now stored in csp_evaluations table via upsert_csp_evaluations().
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.warning("[DEPRECATED] log_csp_candidates() is deprecated. Use upsert_csp_evaluations() instead.")
    # No-op: csp_candidates table no longer exists


def log_alert(message: str, level: str = "INFO") -> None:
    """Log alert to database."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO alerts (message, level, created_at)
        VALUES (?, ?, ?)
    """, (
        message,
        level,
        datetime.now(timezone.utc).isoformat(),
    ))

    conn.commit()
    conn.close()


__all__ = ["init_db", "log_regime_snapshot", "log_csp_candidates", "log_alert", "get_db_path"]
