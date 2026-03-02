# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.2: Trade Ticket v2 — GET ticket, POST journal/from-ticket; no FAIL_/WARN_."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_trade_ticket_endpoint_returns_deterministic_fields() -> None:
    """Ticket endpoint returns expected structure for a given symbol (fixture/mock)."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/trade-ticket?symbol=SPY&strategy=CSP&action=OPEN")
    assert r.status_code == 200
    data = r.json()
    assert "symbol" in data
    assert data["symbol"] == "SPY"
    assert data["strategy"] == "CSP"
    assert data["action"] == "OPEN"
    assert "snapshot_header" in data
    assert "sizing" in data
    assert "execution_steps" in data
    assert isinstance(data["execution_steps"], list)
    assert "journal_draft" in data
    assert "guardrails" in data
    assert "earnings_advisory" in data


def test_trade_ticket_no_fail_warn_in_json() -> None:
    """Ticket response must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/trade-ticket?symbol=SPY&strategy=SHARES&action=BUY")
    assert r.status_code == 200
    raw = json.dumps(r.json())
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_journal_from_ticket_writes_entry() -> None:
    """POST /api/ui/journal/from-ticket creates a journal entry (temp DB)."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "journal.db"
        set_journal_db_path(db)
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                payload = {
                    "trade_date": "2026-02-27",
                    "symbol": "SPY",
                    "strategy": "SHARES",
                    "action": "BUY",
                    "qty": 10,
                    "price": 500.0,
                    "notes": "r262 test",
                    "tags": "r262",
                }
                r = client.post("/api/ui/journal/from-ticket", json=payload)
            assert r.status_code == 200
            body = r.json()
            assert "entry" in body
            assert body["entry"].get("symbol") == "SPY"
            assert body["entry"].get("trade_date") == "2026-02-27"
        finally:
            reset_journal_db_path()


def test_trade_ticket_missing_symbol_returns_400_or_empty_symbol() -> None:
    """Ticket with no symbol returns error or empty symbol in payload."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/trade-ticket?symbol=&strategy=CSP&action=OPEN")
    assert r.status_code == 200
    data = r.json()
    assert data.get("symbol") == "" or "error" in data or "symbol required" in data.get("error", "")
