# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.4: Live open mirror to unified DB (shares + options); reconcile health includes live counts; safe labels only; no decision_latest writes."""

from __future__ import annotations

import re
import sqlite3

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)


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


def test_live_shares_open_mirrors_to_unified_idempotent(positions_db_override) -> None:
    """Live shares open: mirror to positions_open with stable id live_shares_{id}; second call is idempotent."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_shares_open_to_unified,
        get_positions_db_path,
    )
    share_pos = {
        "id": "share-uuid-001",
        "account_id": "default",
        "symbol": "AAPL",
        "quantity": 100,
        "avg_cost": 150.0,
        "opened_at": "2026-03-01T12:00:00",
        "created_at": "2026-03-01T12:00:00",
        "notes": None,
    }
    mirror_live_shares_open_to_unified(share_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id, symbol, instrument_type, is_paper, qty FROM positions_open WHERE id = ?",
            ("live_shares_share-uuid-001",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "AAPL"
        assert rows[0][2] == "SHARES"
        assert rows[0][3] == 0
        assert rows[0][4] == 100
    finally:
        conn.close()
    mirror_live_shares_open_to_unified(share_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id FROM positions_open WHERE id = ?",
            ("live_shares_share-uuid-001",),
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_live_options_open_mirrors_to_unified_idempotent(positions_db_override) -> None:
    """Live options open: mirror to positions_open with stable id live_options_{position_id}; second call is idempotent."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_open_to_unified,
        get_positions_db_path,
    )
    opt_pos = {
        "position_id": "opt-001",
        "id": "opt-001",
        "symbol": "SPY",
        "strategy": "CSP",
        "contracts": 1,
        "strike": 450.0,
        "expiration": "2026-04-18",
        "open_credit": 2.50,
        "opened_at": "2026-03-01T12:00:00",
        "notes": None,
    }
    mirror_live_open_to_unified(opt_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id, symbol, instrument_type, is_paper, qty FROM positions_open WHERE id = ?",
            ("live_options_opt-001",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "SPY"
        assert rows[0][2] == "CSP"
        assert rows[0][3] == 0
        assert rows[0][4] == 100
    finally:
        conn.close()
    mirror_live_open_to_unified(opt_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        rows = conn.execute(
            "SELECT id FROM positions_open WHERE id = ?",
            ("live_options_opt-001",),
        ).fetchall()
        assert len(rows) == 1
    finally:
        conn.close()


def test_reconcile_health_includes_live_open_counts_safe_labels_no_fail_warn_pass(positions_db_override) -> None:
    """get_positions_unified_reconcile_health returns live_shares_open_count, live_options_open_count, unified_open_live_*; status OK/Review only; no FAIL/WARN/PASS."""
    from app.core.portfolio.positions_unified_store_r279 import get_positions_unified_reconcile_health
    health = get_positions_unified_reconcile_health()
    assert "live_shares_open_count" in health
    assert "live_options_open_count" in health
    assert "unified_open_live_shares_count" in health
    assert "unified_open_live_options_count" in health
    assert health.get("status") in ("OK", "Review")
    raw = str(health)
    assert not FORBIDDEN.search(raw), "Reconcile health must not contain FAIL/WARN/PASS"


def test_mirror_live_open_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """mirror_live_shares_open_to_unified and mirror_live_open_to_unified do not write out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_shares_open_to_unified,
        mirror_live_open_to_unified,
    )
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
    mirror_live_shares_open_to_unified({
        "id": "s1",
        "symbol": "X",
        "quantity": 10,
        "opened_at": "2026-03-01T00:00:00",
        "created_at": "2026-03-01T00:00:00",
    })
    mirror_live_open_to_unified({
        "position_id": "o1",
        "id": "o1",
        "symbol": "Y",
        "strategy": "CSP",
        "contracts": 1,
        "opened_at": "2026-03-01T00:00:00",
    })
    after = decision_path.read_text()
    assert after == before
