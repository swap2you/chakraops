# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.8: Reconcile diff — deterministic ordering, safe labels only, no decision write."""

from __future__ import annotations

import json
import re
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
def out_dir_override(tmp_path):
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_reconcile_diff_deterministic_ordering(positions_db_override, out_dir_override) -> None:
    """Diff output is sorted by (symbol, type, id)."""
    from app.core.portfolio.positions_unified_store_r279 import get_reconcile_diff

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
        result = get_reconcile_diff(include_paper=True, limit=50)
    assert "items" in result
    items = result["items"]
    # Order must be deterministic
    for i in range(len(items) - 1):
        a, b = items[i], items[i + 1]
        key_a = ((a.get("symbol") or "").upper(), (a.get("instrument_type") or "").upper(), a.get("id") or "")
        key_b = ((b.get("symbol") or "").upper(), (b.get("instrument_type") or "").upper(), b.get("id") or "")
        assert key_a <= key_b, f"Order violation: {key_a} > {key_b}"


def test_reconcile_diff_filters_symbol_and_include_paper(positions_db_override, out_dir_override) -> None:
    """Diff respects symbol and include_paper."""
    from app.core.portfolio.positions_unified_store_r279 import get_reconcile_diff

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        result = get_reconcile_diff(include_paper=True, symbol="AAPL", limit=200)
    assert "missing_count" in result
    assert "extra_count" in result
    assert "mismatched_count" in result
    assert "items" in result
    assert "status" in result
    assert result["status"] in ("OK", "Review")


def test_reconcile_diff_no_forbidden_tokens_in_payload(positions_db_override, out_dir_override) -> None:
    """Response contains no FAIL/WARN/PASS."""
    from app.core.portfolio.positions_unified_store_r279 import get_reconcile_diff

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        result = get_reconcile_diff(include_paper=True, limit=10)
    raw = json.dumps(result, default=str)
    assert not FORBIDDEN_TOKEN_PATTERN.search(raw), f"Payload contained forbidden token: {raw}"


def test_reconcile_diff_endpoint_no_decision_write(positions_db_override, tmp_path) -> None:
    """GET reconcile-diff does not write decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}')
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/positions/unified/reconcile-diff?include_paper=true&limit=10")
    assert r.status_code == 200
    assert decision_path.read_text().strip() == '{"pre": "existing"}'


def test_reconcile_diff_limit_applied(positions_db_override, out_dir_override) -> None:
    """Items list is capped by limit."""
    from app.core.portfolio.positions_unified_store_r279 import get_reconcile_diff

    # Create many expected positions so we could have many missing
    open_shares = [
        {
            "id": f"det-{i}",
            "symbol": "AAPL",
            "quantity": 100,
            "avg_cost": 150.0,
            "opened_at": "2026-02-01T10:00:00Z",
            "created_at": "2026-02-01T10:00:00Z",
        }
        for i in range(10)
    ]
    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=open_shares), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        result = get_reconcile_diff(include_paper=True, limit=3)
    assert result["missing_count"] == 10
    assert len(result["items"]) <= 3
