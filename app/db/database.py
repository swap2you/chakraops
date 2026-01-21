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


def get_db_path() -> Path:
    """Get path to SQLite database."""
    repo_root = Path(__file__).parent.parent.parent
    db_path = repo_root / "data" / "chakraops.db"
    # Ensure data directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


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

    # Create csp_candidates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS csp_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            score INTEGER NOT NULL,
            reasons TEXT,
            key_levels TEXT,
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_candidates_score ON csp_candidates(score DESC, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC)")

    conn.commit()
    conn.close()


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
    """Log CSP candidates to database (replace old ones)."""
    db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Clear old candidates
    cursor.execute("DELETE FROM csp_candidates")

    # Insert new candidates
    created_at = datetime.utcnow().isoformat()
    for candidate in candidates:
        # Convert numpy/pandas types to native Python types before JSON serialization
        reasons_safe = safe_json(candidate.get("reasons", []))
        key_levels_safe = safe_json(candidate.get("key_levels", {}))
        
        cursor.execute("""
            INSERT INTO csp_candidates (symbol, score, reasons, key_levels, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            candidate["symbol"],
            candidate["score"],
            json.dumps(reasons_safe),
            json.dumps(key_levels_safe),
            created_at,
        ))

    conn.commit()
    conn.close()


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
