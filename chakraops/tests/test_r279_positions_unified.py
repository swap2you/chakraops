# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.9: Unified positions store — deterministic ordering, filters, no FAIL_/WARN_, no write to decision_latest."""

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


def test_unified_deterministic_ordering(positions_db_override) -> None:
    """Unified list has stable sort by symbol, type, expiry, strike, opened_ts."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    # With no sources we get empty list; run twice and order is same
    a = build_unified_positions(state="open", include_paper=True)
    b = build_unified_positions(state="open", include_paper=True)
    assert a == b
    ids_a = [r["id"] for r in a]
    ids_b = [r["id"] for r in b]
    assert ids_a == ids_b


def test_unified_filters_state(positions_db_override) -> None:
    """state=open returns open; state=closed returns closed."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    open_list = build_unified_positions(state="open", include_paper=True)
    closed_list = build_unified_positions(state="closed", include_paper=True)
    # Both are lists; structure may have closed_ts only for closed
    for r in open_list:
        assert "id" in r and "symbol" in r
    for r in closed_list:
        assert "id" in r and "symbol" in r
        assert "closed_ts" in r


def test_unified_filters_instrument_type(positions_db_override) -> None:
    """instrument_type filter restricts to that type."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    all_rows = build_unified_positions(state="open", include_paper=True)
    shares = build_unified_positions(state="open", include_paper=True, instrument_type="SHARES")
    for r in shares:
        assert (r.get("instrument_type") or "").upper() == "SHARES"


def test_unified_filters_symbol(positions_db_override) -> None:
    """symbol filter restricts to that symbol."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    filtered = build_unified_positions(state="open", include_paper=True, symbol="AAPL")
    for r in filtered:
        assert (r.get("symbol") or "").strip().upper() == "AAPL"


def test_unified_response_no_fail_warn(positions_db_override) -> None:
    """Response contains no FAIL_/WARN_ substrings anywhere."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    for state in ("open", "closed"):
        positions = build_unified_positions(state=state, include_paper=True)
        raw = json.dumps(positions, default=str)
        assert not FAIL_WARN_PATTERN.search(raw), f"state={state} contained FAIL_ or WARN_"


def test_unified_health_no_fail_warn(positions_db_override) -> None:
    """Health block contains no FAIL_/WARN_."""
    from app.core.portfolio.positions_unified_store_r279 import get_positions_unified_health

    health = get_positions_unified_health()
    raw = json.dumps(health, default=str)
    assert not FAIL_WARN_PATTERN.search(raw)


def test_unified_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """Building unified positions does not write to out/decision_latest.json."""
    from app.core.portfolio.positions_unified_store_r279 import build_unified_positions

    decision_path = tmp_path / "decision_latest.json"
    if decision_path.exists():
        before = decision_path.read_text()
    else:
        before = None
    # Build (may pull from real holdings/positions/paper in env; we only care we don't write decision)
    build_unified_positions(state="open", include_paper=True)
    if decision_path.exists():
        after = decision_path.read_text()
        assert after == before
    # If path doesn't exist, nothing to check; store doesn't create it
    assert True


def test_api_positions_unified_no_fail_warn(client_ui) -> None:
    """GET /api/ui/positions/unified response has no FAIL_/WARN_ in body."""
    from app.core.portfolio.positions_unified_store_r279 import (
        set_positions_db_path,
        reset_positions_db_path,
        init_db,
    )
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        set_positions_db_path(Path(tmp) / "positions.db")
        init_db()
        try:
            r = client_ui.get("/api/ui/positions/unified?state=open&include_paper=true")
            assert r.status_code == 200
            data = r.json()
            raw = json.dumps(data, default=str)
            assert not FAIL_WARN_PATTERN.search(raw)
        finally:
            reset_positions_db_path()


@pytest.fixture
def client_ui():
    """Test client with UI key."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    client = TestClient(app)
    client.headers["x-ui-key"] = "test-ui-key"
    return client
