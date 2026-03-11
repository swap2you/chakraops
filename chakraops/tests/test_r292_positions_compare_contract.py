# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.2: Stored vs Computed compare — symbol filter parity, deterministic order, no forbidden tokens, no decision write."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)
FORBIDDEN_UNDERSCORE = re.compile(r"FAIL_|WARN_")


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
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_symbol_filter_parity_db_vs_computed(positions_db_override, out_dir_override) -> None:
    """For same symbol and include_paper, /unified and /db return same symbol subset (parity)."""
    from app.core.portfolio.positions_unified_store_r279 import (
        build_unified_positions,
        read_positions_unified_from_db,
        rebuild_positions_unified,
    )

    open_share = {
        "id": "det-1",
        "symbol": "AAPL",
        "quantity": 100,
        "avg_cost": 150.0,
        "opened_at": "2026-02-01T10:00:00Z",
        "created_at": "2026-02-01T10:00:00Z",
    }
    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[open_share]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        rebuild_positions_unified(include_paper=True)

    computed = build_unified_positions(state="open", include_paper=True, symbol="AAPL")
    db_result = read_positions_unified_from_db(state="open", include_paper=True, symbol="AAPL", limit=500)

    assert all((p.get("symbol") or "").upper() == "AAPL" for p in computed)
    assert all((p.get("symbol") or "").upper() == "AAPL" for p in db_result.get("items", []))
    assert len(computed) == db_result.get("count", 0)


def test_deterministic_order_db_and_computed(positions_db_override, out_dir_override) -> None:
    """Both build_unified_positions and read_positions_unified_from_db return deterministically ordered lists."""
    from app.core.portfolio.positions_unified_store_r279 import (
        build_unified_positions,
        read_positions_unified_from_db,
        rebuild_positions_unified,
    )

    open_share = {
        "id": "det-1",
        "symbol": "AAPL",
        "quantity": 100,
        "avg_cost": 150.0,
        "opened_at": "2026-02-01T10:00:00Z",
        "created_at": "2026-02-01T10:00:00Z",
    }
    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[open_share]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        rebuild_positions_unified(include_paper=True)

    computed = build_unified_positions(state="open", include_paper=True)
    db_items = read_positions_unified_from_db(state="open", include_paper=True, limit=100).get("items", [])

    def key(p):
        return (
            (p.get("symbol") or "").upper(),
            (p.get("instrument_type") or "").upper(),
            (p.get("expiry") or "")[:10],
            float(p.get("strike") or 0),
            (p.get("opened_ts") or "")[:26],
        )
    for i in range(len(computed) - 1):
        assert key(computed[i]) <= key(computed[i + 1])
    for i in range(len(db_items) - 1):
        assert key(db_items[i]) <= key(db_items[i + 1])


def test_no_forbidden_tokens_in_payloads(positions_db_override, out_dir_override) -> None:
    """GET /unified and GET /unified/db responses contain no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r1 = client.get("/api/ui/positions/unified?state=open&include_paper=true")
        r2 = client.get("/api/ui/positions/unified/db?state=open&include_paper=true&limit=100")
    assert r1.status_code == 200
    assert r2.status_code == 200
    for data in (r1.json(), r2.json()):
        raw = json.dumps(data, default=str)
        assert not FORBIDDEN.search(raw)
        assert not FORBIDDEN_UNDERSCORE.search(raw)


def test_endpoints_do_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """GET /unified and GET /unified/db do not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path), \
         patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/positions/unified?state=open&include_paper=true")
        client.get("/api/ui/positions/unified/db?state=open&include_paper=true&limit=100")
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
