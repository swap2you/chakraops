# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.0: Share positions DB, API, and CC eligibility (holdings + share_positions)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_share_positions_crud(tmp_path):
    """R23.0: CRUD for share_positions: list, get, upsert, delete."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_file = out_dir / "account.db"
    prev = os.environ.get("CHAKRAOPS_OUT")
    os.environ["CHAKRAOPS_OUT"] = str(out_dir)
    try:
        from app.core.accounts import holdings_db
        # Force fresh DB path (avoid shared repo out)
        with patch.object(holdings_db, "_db_path", return_value=db_file):
            holdings_db.init_db()
            aid = "default"

            # Start clean: delete if present
            holdings_db.delete_share_position(aid, "NVDA")
            assert holdings_db.get_share_position(aid, "NVDA") is None

            # Upsert
            pos = holdings_db.upsert_share_position(aid, "NVDA", 50, avg_cost=100.0)
            assert pos["symbol"] == "NVDA"
            assert pos["quantity"] == 50
            assert pos["avg_cost"] == 100.0
            assert "id" in pos and "updated_at" in pos

            # R25.2: Upsert with target_price, stop_price
            pos2 = holdings_db.upsert_share_position(aid, "NVDA", 50, avg_cost=100.0, target_price=120.0, stop_price=90.0)
            assert pos2.get("target_price") == 120.0
            assert pos2.get("stop_price") == 90.0
            got = holdings_db.get_share_position(aid, "NVDA")
            assert got is not None and got.get("target_price") == 120.0 and got.get("stop_price") == 90.0

            # Get
            got = holdings_db.get_share_position(aid, "NVDA")
            assert got is not None
            assert got["quantity"] == 50

            # Update (upsert same symbol)
            pos2 = holdings_db.upsert_share_position(aid, "nvda", 150, avg_cost=105.0)
            assert pos2["quantity"] == 150
            assert pos2["avg_cost"] == 105.0

            # Delete
            deleted = holdings_db.delete_share_position(aid, "NVDA")
            assert deleted is True
            assert holdings_db.get_share_position(aid, "NVDA") is None
    finally:
        if prev is not None:
            os.environ["CHAKRAOPS_OUT"] = prev
        else:
            os.environ.pop("CHAKRAOPS_OUT", None)


def test_share_positions_validation():
    """R23.0: quantity >= 0, avg_cost >= 0 if provided, symbol normalized."""
    import os
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "out").mkdir(exist_ok=True)
        os.environ["CHAKRAOPS_OUT"] = d + "/out"
        try:
            from app.core.accounts import holdings_db
            holdings_db.init_db()
            with pytest.raises(ValueError, match="quantity"):
                holdings_db.upsert_share_position("default", "AAPL", -1)
            with pytest.raises(ValueError, match="symbol"):
                holdings_db.upsert_share_position("default", "  ", 10)
            pos = holdings_db.upsert_share_position("default", " aapl ", 10)
            assert pos["symbol"] == "AAPL"
        finally:
            os.environ.pop("CHAKRAOPS_OUT", None)


def test_get_total_shares_for_evaluation_merges_holdings_and_share_positions(tmp_path):
    """R23.0: CC eligibility uses total shares = holdings + share_positions."""
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_file = out_dir / "account.db"
    prev = os.environ.get("CHAKRAOPS_OUT")
    os.environ["CHAKRAOPS_OUT"] = str(out_dir)
    try:
        from app.core.accounts import holdings_db
        with patch.object(holdings_db, "_db_path", return_value=db_file):
            holdings_db.init_db()
            aid = "default"
            # Holdings: AAPL 50
            holdings_db.upsert_holding("AAPL", 50)
            # Share position: NVDA 100
            holdings_db.upsert_share_position(aid, "NVDA", 100)
            # Share position: AAPL 60 (adds to same symbol)
            holdings_db.upsert_share_position(aid, "AAPL", 60)
            total = holdings_db.get_total_shares_for_evaluation(aid)
            assert total.get("AAPL") == 110  # 50 + 60
            assert total.get("NVDA") == 100
            # get_holdings_for_evaluation uses default account and same merge
            ev = holdings_db.get_holdings_for_evaluation()
            assert ev.get("AAPL") == 110
            assert ev.get("NVDA") == 100
    finally:
        if prev is not None:
            os.environ["CHAKRAOPS_OUT"] = prev
        else:
            os.environ.pop("CHAKRAOPS_OUT", None)


def test_ui_shares_positions_list_and_upsert_and_delete():
    """R23.0: GET list, POST upsert, DELETE share position via API."""
    pytest.importorskip("fastapi")
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api.server import app
            client = TestClient(app)
            key = os.environ.get("UI_API_KEY") or ""
            headers = {"x-ui-key": key} if key else {}
            # List empty (or existing)
            r = client.get("/api/ui/shares/positions", params={"account_id": "default"}, headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "positions" in data
            # Upsert
            r2 = client.post(
                "/api/ui/shares/positions/NVDA",
                json={"account_id": "default", "quantity": 50, "avg_cost": 200.0},
                headers=headers,
            )
            assert r2.status_code == 200
            pos = r2.json()
            assert pos["symbol"] == "NVDA"
            assert pos["quantity"] == 50
            # List has one
            r3 = client.get("/api/ui/shares/positions", params={"account_id": "default"}, headers=headers)
            assert len(r3.json().get("positions", [])) >= 1
            # Get one
            r4 = client.get("/api/ui/shares/positions/NVDA", params={"account_id": "default"}, headers=headers)
            assert r4.status_code == 200
            # Delete
            r5 = client.delete("/api/ui/shares/positions/NVDA", params={"account_id": "default"}, headers=headers)
            assert r5.status_code == 200
            r6 = client.get("/api/ui/shares/positions/NVDA", params={"account_id": "default"}, headers=headers)
            assert r6.status_code == 404


def test_ui_portfolio_includes_shares_positions():
    """R23.0: GET portfolio includes shares_positions array."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api.server import app
            client = TestClient(app)
            key = os.environ.get("UI_API_KEY") or ""
            headers = {"x-ui-key": key} if key else {}
            r = client.get("/api/ui/portfolio", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert "shares_positions" in data
            assert isinstance(data["shares_positions"], list)
