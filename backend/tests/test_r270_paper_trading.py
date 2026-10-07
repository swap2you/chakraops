# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.0: Paper trading — execute OPEN/CLOSE, journal is_paper, list/summary, no FAIL_/WARN_."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_paper_open_shares_creates_position_and_journal_is_paper() -> None:
    """OPEN shares creates open paper position and journal entry with is_paper=true."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.paper.paper_store_r270 import set_paper_db_path, reset_paper_db_path, init_paper_db, paper_list_positions
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db, journal_list

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        set_journal_db_path(Path(tmp) / "journal.db")
        init_paper_db()
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/paper/execute",
                    json={
                        "mode": "PAPER",
                        "symbol": "SPY",
                        "strategy": "SHARES",
                        "action": "OPEN",
                        "qty": 10,
                        "shares_price": 450.5,
                        "fees": 1.0,
                    },
                )
                assert r.status_code == 200
                data = r.json()
                assert data.get("status") == "OK"
                pos = data.get("position", {})
                assert pos.get("symbol") == "SPY"
                assert pos.get("strategy") == "SHARES"
                assert pos.get("qty") == 10
                assert pos.get("status") == "OPEN"
                assert pos.get("open_price") == 450.5
                positions = paper_list_positions(status="OPEN")
                assert len(positions) >= 1
                entries = journal_list(limit=10, include_paper=True)
                paper_entries = [e for e in entries if e.get("link_id", "").startswith("paper:")]
                assert len(paper_entries) >= 1
                assert paper_entries[0].get("is_paper") == 1
        finally:
            reset_paper_db_path()
            reset_journal_db_path()


def test_paper_close_shares_computes_realized_pl() -> None:
    """CLOSE shares closes position and realized_pl is computed."""
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_execute_close,
        paper_list_positions,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        init_paper_db()
        try:
            pos = paper_execute_open("QQQ", "SHARES", 5, 400.0, 0)
            pos_id = pos["id"]
            closed = paper_execute_close(position_id=pos_id, close_price=410.0, close_fees=0)
            assert closed.get("status") == "CLOSED"
            assert closed.get("realized_pl") is not None
            expected_pl = (410 - 400) * 5
            assert abs(closed["realized_pl"] - expected_pl) < 0.01
        finally:
            reset_paper_db_path()


def test_paper_open_csp_creates_option_position() -> None:
    """OPEN CSP creates option position with contract fields."""
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_list_positions,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        init_paper_db()
        try:
            pos = paper_execute_open(
                "SPY", "CSP", 1, 2.5, 0,
                contract_key="SPY250321P00450000",
                expiry="2025-03-21",
                strike=450,
                right="P",
            )
            assert pos.get("instrument_type") == "OPTION"
            assert pos.get("contract_key") == "SPY250321P00450000"
            assert pos.get("expiry") == "2025-03-21"
            assert pos.get("strike") == 450
        finally:
            reset_paper_db_path()


def test_paper_close_csp_realized_pl() -> None:
    """CLOSE CSP closes and realized_pl computed (premium-based)."""
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_execute_close,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        init_paper_db()
        try:
            pos = paper_execute_open("SPY", "CSP", 2, 3.0, 0)
            closed = paper_execute_close(position_id=pos["id"], close_price=1.0, close_fees=0)
            assert closed.get("status") == "CLOSED"
            assert closed.get("realized_pl") is not None
            expected = (3.0 - 1.0) * 2 * 100
            assert abs(closed["realized_pl"] - expected) < 0.01
        finally:
            reset_paper_db_path()


def test_paper_list_and_summary() -> None:
    """List positions and summary filter correctly."""
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_execute_close,
        paper_list_positions,
        paper_summary_by_month,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        init_paper_db()
        try:
            pos = paper_execute_open("SPY", "SHARES", 1, 100.0, 0, ts="2026-02-15T12:00:00Z")
            paper_execute_close(position_id=pos["id"], close_price=105.0, close_fees=0, ts="2026-02-15T14:00:00Z")
            open_list = paper_list_positions(status="OPEN")
            closed_list = paper_list_positions(status="CLOSED")
            assert len(closed_list) >= 1
            summary = paper_summary_by_month("2026-02")
            assert summary.get("trade_count") >= 1
            assert summary.get("realized_pl") is not None
        finally:
            reset_paper_db_path()


def test_paper_api_no_fail_warn_in_json() -> None:
    """Paper API responses must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.paper.paper_store_r270 import set_paper_db_path, reset_paper_db_path, init_paper_db
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        set_journal_db_path(Path(tmp) / "journal.db")
        init_paper_db()
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/paper/execute",
                    json={"mode": "PAPER", "symbol": "AAPL", "strategy": "SHARES", "action": "OPEN", "qty": 1, "shares_price": 180},
                )
                assert r.status_code == 200
                raw = json.dumps(r.json())
                assert "FAIL_" not in raw
                assert "WARN_" not in raw
                r2 = client.get("/api/ui/paper/positions")
                assert r2.status_code == 200
                assert "FAIL_" not in json.dumps(r2.json())
                assert "WARN_" not in json.dumps(r2.json())
                r3 = client.get("/api/ui/paper/summary?month=2026-02")
                assert r3.status_code == 200
                assert "FAIL_" not in json.dumps(r3.json())
                assert "WARN_" not in json.dumps(r3.json())
        finally:
            reset_paper_db_path()
            reset_journal_db_path()
