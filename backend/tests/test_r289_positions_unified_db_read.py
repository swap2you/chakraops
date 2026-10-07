# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.9: DB-first read — deterministic order, filters, no forbidden tokens, no decision write."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from unittest.mock import patch

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
def seeded_db(positions_db_override):
    """Seed positions_open with deterministic rows."""
    db_path = positions_db_override
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """INSERT INTO positions_open (id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                ("paper_1", "AAPL", "SHARES", 1, 100, 150.0, None, None, None, "2026-02-01T10:00:00", "1", None, None),
                ("live_shares_2", "SPY", "SHARES", 0, 50, 400.0, None, None, None, "2026-02-02T11:00:00", "2", None, None),
                ("paper_3", "AAPL", "CSP", 1, 100, 1.5, 150.0, "2027-03-20", "P", "2026-02-03T09:00:00", "3", None, None),
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_db_read_open_deterministic_order(positions_db_override, seeded_db) -> None:
    """DB read returns items in deterministic order (symbol, type, expiry, strike, opened_ts)."""
    from app.core.portfolio.positions_unified_store_r279 import read_positions_unified_from_db

    result = read_positions_unified_from_db(state="open", include_paper=True, limit=100)
    assert result["status"] == "OK"
    assert "items" in result
    items = result["items"]
    assert len(items) == 3
    for i in range(len(items) - 1):
        a, b = items[i], items[i + 1]
        key_a = _sort_key_for_item(a)
        key_b = _sort_key_for_item(b)
        assert key_a <= key_b, f"Order violation: {key_a} > {key_b}"


def _sort_key_for_item(row):
    sym = (row.get("symbol") or "").strip().upper()
    itype = (row.get("instrument_type") or "").upper()
    expiry = (row.get("expiry") or "")[:10]
    strike = float(row.get("strike") or 0)
    opened = (row.get("opened_ts") or "")[:26]
    return (sym, itype, expiry, strike, opened)


def test_db_read_filters_symbol_and_type(positions_db_override, seeded_db) -> None:
    """DB read respects symbol and instrument_type filters."""
    from app.core.portfolio.positions_unified_store_r279 import read_positions_unified_from_db

    r = read_positions_unified_from_db(state="open", include_paper=True, symbol="AAPL", limit=100)
    assert r["status"] == "OK"
    assert r["count"] == 2  # paper_1 AAPL SHARES, paper_3 AAPL CSP
    for item in r["items"]:
        assert (item.get("symbol") or "").upper() == "AAPL"

    r2 = read_positions_unified_from_db(state="open", include_paper=True, instrument_type="SHARES", limit=100)
    assert r2["status"] == "OK"
    for item in r2["items"]:
        assert (item.get("instrument_type") or "").upper() == "SHARES"


def test_db_read_include_paper_filter(positions_db_override, seeded_db) -> None:
    """DB read with include_paper=false returns only is_paper=0."""
    from app.core.portfolio.positions_unified_store_r279 import read_positions_unified_from_db

    r = read_positions_unified_from_db(state="open", include_paper=False, limit=100)
    assert r["status"] == "OK"
    assert r["count"] == 1
    assert r["items"][0].get("id") == "live_shares_2"
    assert r["items"][0].get("is_paper") == 0


def test_db_read_has_no_fail_warn_pass_tokens_in_payload(positions_db_override, seeded_db) -> None:
    """Response contains no FAIL/WARN/PASS."""
    from app.core.portfolio.positions_unified_store_r279 import read_positions_unified_from_db

    result = read_positions_unified_from_db(state="open", include_paper=True, limit=10)
    raw = json.dumps(result, default=str)
    assert not FORBIDDEN_TOKEN_PATTERN.search(raw), f"Payload contained forbidden token: {raw}"


def test_db_read_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """DB read endpoint does not write decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}')
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/positions/unified/db?state=open&include_paper=true&limit=10")
    assert r.status_code == 200
    assert decision_path.read_text().strip() == '{"pre": "existing"}'
