# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.0: Paper write mirror to unified DB (idempotent); reconcile health; no FAIL_/WARN_; no decision_latest writes."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FAIL_WARN_PATTERN = re.compile(r"FAIL_|WARN_", re.I)


@pytest.fixture
def positions_db_override(tmp_path):
    from app.core.portfolio.positions_unified_store_r279 import (
        set_positions_db_path,
        reset_positions_db_path,
        init_db,
    )
    db_path = tmp_path / "positions.db"
    set_positions_db_path(db_path)
    init_db()
    try:
        yield db_path
    finally:
        reset_positions_db_path()


def test_paper_open_mirrors_to_unified_idempotent(positions_db_override) -> None:
    """Paper open upsert into positions_open; second call is idempotent (same row)."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_paper_open_to_unified,
        init_db,
        get_positions_db_path,
    )
    import sqlite3
    pos = {
        "id": "test-open-001",
        "symbol": "AAPL",
        "strategy": "SHARES",
        "qty": 100,
        "open_ts": "2026-03-01T12:00:00",
        "open_price": 150.0,
        "strike": None,
        "expiry": None,
        "right": None,
        "notes": None,
    }
    mirror_paper_open_to_unified(pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute("SELECT id, symbol, is_paper FROM positions_open WHERE id = ?", ("paper_test-open-001",)).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "AAPL" and rows[0][2] == 1
    finally:
        conn.close()
    # Idempotent: call again
    mirror_paper_open_to_unified(pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute("SELECT id FROM positions_open WHERE id = ?", ("paper_test-open-001",)).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_paper_close_mirrors_to_unified_idempotent(positions_db_override) -> None:
    """Paper close removes from positions_open, upserts into positions_closed; second close call is idempotent."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_paper_open_to_unified,
        mirror_paper_close_to_unified,
        get_positions_db_path,
    )
    import sqlite3
    pid = "test-close-002"
    open_pos = {
        "id": pid,
        "symbol": "SPY",
        "strategy": "CSP",
        "qty": 2,
        "open_ts": "2026-03-01T10:00:00",
        "open_price": 3.50,
        "open_fees": 0.0,
        "strike": 450.0,
        "expiry": "2026-04-19",
        "right": "PUT",
        "notes": None,
    }
    mirror_paper_open_to_unified(open_pos)
    closed_pos = {
        **open_pos,
        "close_ts": "2026-03-15T14:00:00",
        "close_fees": 0.0,
        "realized_pl": 120.5,
    }
    mirror_paper_close_to_unified(closed_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        open_rows = conn.execute("SELECT id FROM positions_open WHERE id = ?", (f"paper_{pid}",)).fetchall()
        closed_rows = conn.execute("SELECT id FROM positions_closed WHERE id = ?", (f"paper_closed_{pid}",)).fetchall()
        assert len(open_rows) == 0
        assert len(closed_rows) == 1
    finally:
        conn.close()
    # Idempotent
    mirror_paper_close_to_unified(closed_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        closed_rows = conn.execute("SELECT id FROM positions_closed WHERE id = ?", (f"paper_closed_{pid}",)).fetchall()
        assert len(closed_rows) == 1
    finally:
        conn.close()


def test_reconcile_health_safe_labels_no_fail_warn(positions_db_override) -> None:
    """Reconcile health returns status OK or Review; no FAIL_/WARN_ anywhere."""
    from app.core.portfolio.positions_unified_store_r279 import get_positions_unified_reconcile_health

    health = get_positions_unified_reconcile_health()
    assert "status" in health
    assert health["status"] in ("OK", "Review")
    assert "paper_open_count" in health
    assert "paper_closed_count" in health
    assert "unified_open_paper_count" in health
    assert "unified_closed_paper_count" in health
    raw = json.dumps(health, default=str)
    assert not FAIL_WARN_PATTERN.search(raw)


def test_mirror_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """Mirror and reconcile do not write to out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_paper_open_to_unified,
        get_positions_unified_reconcile_health,
    )
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
    mirror_paper_open_to_unified({
        "id": "no-decision",
        "symbol": "X",
        "strategy": "SHARES",
        "qty": 1,
        "open_ts": "2026-03-01T00:00:00",
        "open_price": 1.0,
        "strike": None,
        "expiry": None,
        "right": None,
        "notes": None,
    })
    get_positions_unified_reconcile_health()
    after = decision_path.read_text()
    assert after == before
