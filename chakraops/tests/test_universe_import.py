# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Universe import from CSV (idempotent upsert)."""

from __future__ import annotations

import csv
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.db.universe_import import (
    import_universe_from_csv,
    canonical_to_provider_symbol,
    DEFAULT_CSV_NAME,
)


def test_canonical_to_provider_symbol_brk_b() -> None:
    assert canonical_to_provider_symbol("BRK.B", "yfinance") == "BRK-B"
    assert canonical_to_provider_symbol("brk.b", "yfinance") == "BRK-B"


def test_canonical_to_provider_symbol_passthrough() -> None:
    assert canonical_to_provider_symbol("AAPL", "yfinance") == "AAPL"


def test_import_universe_from_csv_idempotent(tmp_path: Path) -> None:
    csv_path = tmp_path / "watchlist.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol"])
        w.writerow(["AAPL"])
        w.writerow(["MSFT"])
    db_path = tmp_path / "test.db"
    with pytest.MonkeyPatch.context() as m:
        m.setattr("app.db.database.get_db_path", lambda: db_path)
        m.setattr("app.core.persistence.get_db_path", lambda: db_path)
        m.setattr("app.db.universe_import.get_db_path", lambda: db_path)
        init_persistence_db = __import__("app.core.persistence", fromlist=["init_persistence_db"]).init_persistence_db
        init_persistence_db()
        n1 = import_universe_from_csv(csv_path=csv_path, notes="core_watchlist")
        n2 = import_universe_from_csv(csv_path=csv_path, notes="core_watchlist")
    assert n1 == 2
    assert n2 == 2
    conn = sqlite3.connect(str(db_path))
    cur = conn.execute("SELECT symbol, enabled, notes FROM symbol_universe WHERE notes = ? ORDER BY symbol", ("core_watchlist",))
    rows = cur.fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0][0] == "AAPL" and rows[0][1] == 1 and rows[0][2] == "core_watchlist"
    assert rows[1][0] == "MSFT"
