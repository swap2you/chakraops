# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe import from CSV (Phase 8.3). Upsert symbol_universe; optional provider symbol mapping."""

from __future__ import annotations

import csv
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from app.core.persistence import init_persistence_db
from app.db.database import get_db_path

logger = logging.getLogger(__name__)

# Default CSV path (configurable via UNIVERSE_CSV_PATH)
DEFAULT_CSV_NAME = "ChakraOps_Core_Watchlist.csv"


def _repo_root() -> Path:
    """ChakraOps repo root (chakraops/). app/db/universe_import.py -> parents[2] = chakraops."""
    return Path(__file__).resolve().parents[2]


def _default_csv_path() -> Path:
    return _repo_root() / DEFAULT_CSV_NAME


def get_effective_universe_csv_path() -> Path:
    """Path used for import: UNIVERSE_CSV_PATH env or default. For UI display."""
    return Path(os.getenv("UNIVERSE_CSV_PATH", str(_default_csv_path())))


def canonical_to_provider_symbol(symbol: str, provider: str = "yfinance") -> str:
    """Map canonical symbol to provider format (e.g. BRK.B -> BRK-B for yfinance). Store canonical in DB."""
    if not symbol:
        return symbol
    s = str(symbol).strip().upper()
    # Common mappings: dot to hyphen for some providers
    if provider == "yfinance":
        if s == "BRK.B":
            return "BRK-B"
        if s == "BRK.A":
            return "BRK-A"
    return s


def import_universe_from_csv(
    csv_path: Optional[Path] = None,
    notes: str = "core_watchlist",
    enabled: bool = True,
) -> int:
    """Read ChakraOps_Core_Watchlist.csv (or path from UNIVERSE_CSV_PATH), UPSERT symbol_universe with enabled=1.
    Uses INSERT ... ON CONFLICT(symbol) DO UPDATE SET enabled=1. Returns count upserted. No silent failures."""
    path = csv_path or get_effective_universe_csv_path()
    if not isinstance(path, Path):
        path = Path(path)
    path = path.resolve()
    if not path.exists():
        msg = f"Universe CSV not found: {path}"
        logger.error(msg)
        print(msg)
        return 0
    init_persistence_db()
    db_path = get_db_path()
    symbols: List[str] = []
    notes_from_csv: Dict[str, str] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        key = None
        for col in ("symbol", "Symbol", "ticker", "Ticker"):
            if col in fieldnames:
                key = col
                break
        if not key and fieldnames:
            key = fieldnames[0]
        notes_col = "notes" if "notes" in fieldnames else ("name" if "name" in fieldnames else None)
        for row in reader:
            if not row:
                continue
            val = row.get(key, "") if key else (list(row.values())[0] if row else "")
            if val and str(val).strip():
                sym = str(val).strip().upper()
                symbols.append(sym)
                if notes_col and row.get(notes_col):
                    notes_from_csv[sym] = str(row.get(notes_col, "")).strip()
    if not symbols:
        msg = f"No symbols in CSV: {path}"
        logger.warning(msg)
        print(msg)
        return 0
    created_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbol_universe (
                symbol TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                notes TEXT,
                created_at TEXT NOT NULL
            )
        """)
        count = 0
        for sym in symbols:
            row_notes = notes_from_csv.get(sym) or notes
            cursor.execute("""
                INSERT INTO symbol_universe (symbol, enabled, notes, created_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    enabled = 1,
                    notes = excluded.notes,
                    created_at = excluded.created_at
            """, (sym, row_notes, created_at))
            count += 1
        conn.commit()
        msg = f"Universe import: {count} symbols upserted from {path.name} (enabled=1)"
        logger.info(msg)
        print(msg)
        return count
    finally:
        conn.close()


__all__ = ["import_universe_from_csv", "canonical_to_provider_symbol", "get_effective_universe_csv_path", "DEFAULT_CSV_NAME"]
