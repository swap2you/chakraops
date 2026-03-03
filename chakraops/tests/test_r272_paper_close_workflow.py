# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.2: Paper close workflow — POST /api/ui/paper/close, journal CLOSE_*/SELL, no FAIL_/WARN_, determinism."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_paper_close_shares_via_api_realized_pl_and_journal() -> None:
    """Create OPEN paper shares, close via POST /paper/close; realized_pl correct; journal entry is_paper=true, action SELL."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_list_positions,
    )
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_list,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        set_journal_db_path(Path(tmp) / "journal.db")
        init_paper_db()
        init_journal_db()
        try:
            pos = paper_execute_open("SPY", "SHARES", 10, 450.0, 0)
            pos_id = pos["id"]
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/paper/close",
                    json={
                        "position_id": pos_id,
                        "close_price": 455.0,
                        "close_fees": 1.0,
                        "ts": "2026-02-27T15:00:00Z",
                    },
                )
            assert r.status_code == 200
            data = r.json()
            raw = json.dumps(data)
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
            assert data.get("status") == "OK"
            closed = data.get("position", {})
            assert closed.get("status") == "CLOSED"
            expected_pl = (455.0 - 450.0) * 10 - 0 - 1.0
            assert abs((closed.get("realized_pl") or 0) - expected_pl) < 0.01
            entries = journal_list(limit=20, include_paper=True)
            close_entries = [e for e in entries if e.get("link_id") == f"paper:{closed.get('id')}"]
            assert len(close_entries) >= 1
            entry = close_entries[0]
            assert entry.get("is_paper") == 1
            assert (entry.get("action") or "").upper() == "SELL"
            assert entry.get("realized_pl") is not None
            assert abs(entry["realized_pl"] - expected_pl) < 0.01
            open_list = paper_list_positions(status="OPEN")
            assert not any(p.get("id") == pos_id for p in open_list)
        finally:
            reset_paper_db_path()
            reset_journal_db_path()


def test_paper_close_csp_via_api_premium_math_and_journal() -> None:
    """Close paper CSP via POST /paper/close; premium math (open credit vs close debit) correct; journal CLOSE_CSP."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_list_positions,
    )
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_list,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        set_journal_db_path(Path(tmp) / "journal.db")
        init_paper_db()
        init_journal_db()
        try:
            pos = paper_execute_open(
                "SPY", "CSP", 1, 2.5, 0,
                contract_key="SPY250321P00450000",
                expiry="2025-03-21",
                strike=450,
                right="P",
            )
            pos_id = pos["id"]
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/paper/close",
                    json={
                        "position_id": pos_id,
                        "close_premium": 1.0,
                        "close_fees": 0,
                    },
                )
            assert r.status_code == 200
            data = r.json()
            raw = json.dumps(data)
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
            assert data.get("status") == "OK"
            closed = data.get("position", {})
            assert closed.get("status") == "CLOSED"
            expected_pl = (2.5 - 1.0) * 1 * 100 - 0 - 0
            assert abs((closed.get("realized_pl") or 0) - expected_pl) < 0.01
            entries = journal_list(limit=20, include_paper=True)
            close_entries = [e for e in entries if e.get("link_id") == f"paper:{closed.get('id')}"]
            assert len(close_entries) >= 1
            entry = close_entries[0]
            assert entry.get("is_paper") == 1
            assert (entry.get("action") or "").upper() == "CLOSE_CSP"
        finally:
            reset_paper_db_path()
            reset_journal_db_path()


def test_paper_close_api_no_fail_warn_in_response() -> None:
    """POST /paper/close and GET /paper/positions responses must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
    )
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db

    with tempfile.TemporaryDirectory() as tmp:
        set_paper_db_path(Path(tmp) / "paper.db")
        set_journal_db_path(Path(tmp) / "journal.db")
        init_paper_db()
        init_journal_db()
        try:
            pos = paper_execute_open("QQQ", "SHARES", 5, 400.0, 0)
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/paper/close",
                    json={"position_id": pos["id"], "close_price": 405.0, "close_fees": 0},
                )
            assert r.status_code == 200
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
            r2 = client.get("/api/ui/paper/positions?status=CLOSED")
            assert r2.status_code == 200
            assert "FAIL_" not in json.dumps(r2.json())
            assert "WARN_" not in json.dumps(r2.json())
        finally:
            reset_paper_db_path()
            reset_journal_db_path()


def test_paper_close_deterministic_same_inputs_same_realized_pl() -> None:
    """Same position closed twice (in separate DBs) with same inputs yields same realized_pl and payload shape."""
    from app.core.paper.paper_store_r270 import (
        set_paper_db_path,
        reset_paper_db_path,
        init_paper_db,
        paper_execute_open,
        paper_execute_close,
    )

    def close_once(tmp: str) -> float:
        set_paper_db_path(Path(tmp) / "paper.db")
        init_paper_db()
        pos = paper_execute_open("SPY", "SHARES", 10, 450.0, 0.5)
        closed = paper_execute_close(position_id=pos["id"], close_price=455.0, close_fees=1.0)
        return float(closed.get("realized_pl", 0))

    with tempfile.TemporaryDirectory() as tmp1:
        with tempfile.TemporaryDirectory() as tmp2:
            pl1 = close_once(tmp1)
            reset_paper_db_path()
            pl2 = close_once(tmp2)
            reset_paper_db_path()
            expected = (455.0 - 450.0) * 10 - 0.5 - 1.0
            assert abs(pl1 - expected) < 0.01
            assert abs(pl2 - expected) < 0.01
            assert pl1 == pl2
