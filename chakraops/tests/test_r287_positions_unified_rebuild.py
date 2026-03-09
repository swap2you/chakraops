# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.7: Unified positions rebuild — idempotent/deterministic, safe labels only, no decision artifact, state file safe."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

FORBIDDEN_TOKEN_PATTERN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)


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


@pytest.fixture
def out_dir_override(tmp_path):
    """Patch decision store path so out/ is tmp_path; state file and decision_latest live there."""
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_rebuild_is_idempotent_and_deterministic_counts(positions_db_override, out_dir_override) -> None:
    """Rebuild twice yields same counts and stable ordering in GET unified positions."""
    from app.core.portfolio.positions_unified_store_r279 import (
        rebuild_positions_unified,
        build_unified_positions,
    )
    import sqlite3

    # Deterministic fixture: mock sources to return fixed small data
    open_share = {
        "id": "det-share-1",
        "symbol": "AAPL",
        "quantity": 100,
        "avg_cost": 150.0,
        "opened_at": "2026-02-01T10:00:00Z",
        "created_at": "2026-02-01T10:00:00Z",
    }
    closed_share = {
        "id": "det-share-closed-1",
        "symbol": "SPY",
        "quantity": 50,
        "avg_cost": 400.0,
        "opened_at": "2026-01-01T10:00:00Z",
        "closed_at": "2026-02-01T12:00:00Z",
        "realized_pnl": 100.0,
    }

    def mock_list_share_positions(account_id):
        return [open_share]

    def mock_list_closed_share_positions(account_id):
        return [closed_share]

    with patch("app.core.accounts.holdings_db.list_share_positions", side_effect=mock_list_share_positions), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", side_effect=mock_list_closed_share_positions), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        res1 = rebuild_positions_unified(include_paper=True)
        res2 = rebuild_positions_unified(include_paper=True)

    assert res1.get("status") == "OK"
    assert res2.get("status") == "OK"
    assert res1.get("rebuilt_open") == res2.get("rebuilt_open")
    assert res1.get("rebuilt_closed") == res2.get("rebuilt_closed")

    db_path = positions_db_override
    conn = sqlite3.connect(str(db_path))
    try:
        open_rows = conn.execute("SELECT id FROM positions_open ORDER BY symbol, instrument_type, expiry, strike, opened_ts").fetchall()
        closed_rows = conn.execute("SELECT id FROM positions_closed ORDER BY symbol, instrument_type, expiry, strike, opened_ts, closed_ts").fetchall()
    finally:
        conn.close()
    ids_open = [r[0] for r in open_rows]
    ids_closed = [r[0] for r in closed_rows]
    assert len(ids_open) == res1.get("rebuilt_open")
    assert len(ids_closed) == res1.get("rebuilt_closed")
    # Second rebuild should produce same IDs in same order
    with patch("app.core.accounts.holdings_db.list_share_positions", side_effect=mock_list_share_positions), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", side_effect=mock_list_closed_share_positions), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        res2_again = rebuild_positions_unified(include_paper=True)
    conn = sqlite3.connect(str(db_path))
    try:
        open_rows2 = conn.execute("SELECT id FROM positions_open ORDER BY symbol, instrument_type, expiry, strike, opened_ts").fetchall()
    finally:
        conn.close()
    ids_open2 = [r[0] for r in open_rows2]
    assert ids_open == ids_open2


def test_rebuild_endpoint_safe_labels_no_fail_warn_pass(positions_db_override, out_dir_override) -> None:
    """POST rebuild response contains only safe status/status_label and no forbidden tokens."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    r = client.post("/api/ui/positions/unified/rebuild?include_paper=true")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    result = data.get("result") or {}
    assert "status" in result
    assert "status_label" in result
    raw = json.dumps(data, default=str)
    assert not FORBIDDEN_TOKEN_PATTERN.search(raw), f"Response contained FAIL/WARN/PASS: {raw}"


def test_rebuild_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """Rebuild does not create or modify out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import rebuild_positions_unified

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}')
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        rebuild_positions_unified(include_paper=True)
    assert decision_path.read_text().strip() == '{"pre": "existing"}'


def test_rebuild_state_file_has_no_forbidden_tokens(positions_db_override, out_dir_override) -> None:
    """After rebuild, positions_unified_rebuild_state.json contains no FAIL/WARN/PASS."""
    from app.core.portfolio.positions_unified_store_r279 import (
        rebuild_positions_unified,
        _rebuild_state_path,
    )

    rebuild_positions_unified(include_paper=True)
    path = _rebuild_state_path()
    assert path.exists(), "State file should exist after rebuild"
    content = path.read_text(encoding="utf-8")
    assert not FORBIDDEN_TOKEN_PATTERN.search(content), f"State file contained forbidden token: {content}"
