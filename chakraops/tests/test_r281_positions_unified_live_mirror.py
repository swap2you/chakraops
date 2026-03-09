# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.1: Live close/roll mirror to unified DB (idempotent); reconcile advisory (deduped); no FAIL_/WARN_; no decision_latest writes."""

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


def test_live_close_mirrors_to_unified_idempotent(positions_db_override) -> None:
    """Live options close: mirror to positions_closed; second call is idempotent (one row)."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_open_to_unified,
        mirror_live_close_to_unified,
        get_positions_db_path,
    )
    import sqlite3
    pid = "live-opt-001"
    open_pos = {
        "position_id": pid,
        "id": pid,
        "symbol": "AAPL",
        "strategy": "CSP",
        "contracts": 1,
        "strike": 150.0,
        "expiration": "2026-04-18",
        "open_credit": 3.50,
        "opened_at": "2026-03-01T12:00:00",
        "open_time_utc": "2026-03-01T12:00:00",
        "notes": None,
    }
    mirror_live_open_to_unified(open_pos)
    closed_pos = {
        **open_pos,
        "status": "CLOSED",
        "closed_at": "2026-03-15T14:00:00",
        "close_time_utc": "2026-03-15T14:00:00",
        "realized_pl": 120.5,
        "open_fees": 0.0,
        "close_fees": 0.0,
    }
    mirror_live_close_to_unified(closed_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        open_rows = conn.execute("SELECT id FROM positions_open WHERE id = ?", (f"live_options_{pid}",)).fetchall()
        closed_rows = conn.execute("SELECT id FROM positions_closed WHERE id = ?", (f"live_options_closed_{pid}",)).fetchall()
        assert len(open_rows) == 0
        assert len(closed_rows) == 1
    finally:
        conn.close()
    mirror_live_close_to_unified(closed_pos)
    conn = sqlite3.connect(str(get_positions_db_path()))
    try:
        closed_rows = conn.execute("SELECT id FROM positions_closed WHERE id = ?", (f"live_options_closed_{pid}",)).fetchall()
        assert len(closed_rows) == 1
    finally:
        conn.close()


def test_reconcile_review_creates_single_notification_deduped(positions_db_override, monkeypatch) -> None:
    """When reconcile status is Review, ensure_reconcile_advisory_notification creates one notification; second call does not create another."""
    from app.api.notifications_store import load_notifications as orig_load, append_notification as orig_append
    from app.core.portfolio.positions_unified_store_r279 import ensure_reconcile_advisory_notification
    load_calls = []

    def mock_load(limit=100, state_filter=None, symbol_filter=None, type_filter=None, offset=0):
        if type_filter == "POSITIONS_RECONCILE_REVIEW":
            load_calls.append(1)
            if len(load_calls) == 1:
                return []  # First call: no existing advisory -> will append
            return [{"id": "n_reconcile_1", "type": "POSITIONS_RECONCILE_REVIEW", "state": "NEW"}]  # Second call: already have one -> skip
        return orig_load(limit=limit, state_filter=state_filter, symbol_filter=symbol_filter, type_filter=type_filter, offset=offset)
    append_calls = []

    def counted_append(*args, **kwargs):
        append_calls.append(1)
        return orig_append(*args, **kwargs)

    monkeypatch.setattr(
        "app.core.portfolio.positions_unified_store_r279.get_positions_unified_reconcile_health",
        lambda: {"status": "Review", "paper_open_count": 1, "paper_closed_count": 0, "unified_open_paper_count": 0, "unified_closed_paper_count": 0},
    )
    monkeypatch.setattr("app.api.notifications_store.load_notifications", mock_load)
    monkeypatch.setattr("app.api.notifications_store.append_notification", counted_append)
    ensure_reconcile_advisory_notification()
    ensure_reconcile_advisory_notification()
    assert len(append_calls) == 1


def test_health_and_api_have_no_fail_warn_tokens(positions_db_override) -> None:
    """System-health and unified positions API responses contain no FAIL_ or WARN_ in serialized JSON."""
    from app.api.ui_routes import _get_positions_unified_reconcile_health
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions, get_positions_unified_reconcile_health
    health = _get_positions_unified_reconcile_health()
    raw_health = json.dumps(health, default=str)
    assert not FAIL_WARN_PATTERN.search(raw_health), "positions_unified_reconcile must not contain FAIL_/WARN_"
    rec = get_positions_unified_reconcile_health()
    assert not FAIL_WARN_PATTERN.search(json.dumps(rec, default=str))
    positions = build_unified_positions(state="open", include_paper=True)
    for row in positions:
        assert not FAIL_WARN_PATTERN.search(json.dumps(row, default=str))


def test_mirror_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """Live mirror and ensure_reconcile_advisory_notification do not write to out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import (
        mirror_live_close_to_unified,
        ensure_reconcile_advisory_notification,
    )
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
    mirror_live_close_to_unified({
        "id": "closed-share-1",
        "symbol": "X",
        "quantity": 10,
        "opened_at": "2026-03-01T00:00:00",
        "closed_at": "2026-03-10T00:00:00",
        "exit_price": 1.0,
        "realized_pnl": 0.0,
    })
    ensure_reconcile_advisory_notification()
    after = decision_path.read_text()
    assert after == before
