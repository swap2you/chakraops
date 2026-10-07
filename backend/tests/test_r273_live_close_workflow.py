# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.3: Live shares close + options record-close — journal entries, no FAIL_/WARN_."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_shares_close_creates_journal_entry_and_realized_pl_matches() -> None:
    """Close live shares via POST /shares/positions/{symbol}/close; journal entry is_paper=false, SELL, link_id=shares:{symbol}:{id}; realized_pl matches."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.accounts import holdings_db
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db, journal_list

    with tempfile.TemporaryDirectory() as out_dir_str:
        out_dir = Path(out_dir_str)
        db_file = out_dir / "account.db"
        journal_file = out_dir / "journal.db"
        set_journal_db_path(journal_file)
        init_journal_db()
        try:
            with patch.object(holdings_db, "_db_path", return_value=db_file):
                holdings_db.init_db()
                holdings_db.delete_share_position("default", "SPY")
                pos = holdings_db.upsert_share_position("default", "SPY", 10, avg_cost=100.0)
                assert pos["symbol"] == "SPY" and pos["quantity"] == 10
                with patch("app.api.ui_routes._require_ui_key"):
                    client = TestClient(app)
                    r = client.post(
                        "/api/ui/shares/positions/SPY/close",
                        json={
                            "account_id": "default",
                            "exit_price": 105.0,
                            "fees": 1.0,
                            "notes": "R27.3 test",
                        },
                    )
                assert r.status_code == 200
                raw = json.dumps(r.json())
                assert "FAIL_" not in raw
                assert "WARN_" not in raw
                closed = r.json()
                assert closed.get("symbol") == "SPY"
                assert closed.get("realized_pnl") is not None
                expected_pnl = (105.0 - 100.0) * 10
                assert abs(closed["realized_pnl"] - expected_pnl) < 0.01
                entries = journal_list(limit=20, include_paper=False)
                share_entries = [e for e in entries if (e.get("link_id") or "").startswith("shares:SPY:")]
                assert len(share_entries) >= 1
                entry = share_entries[0]
                assert entry.get("is_paper") == 0
                assert (entry.get("action") or "").upper() == "SELL"
                assert entry.get("strategy") == "SHARES"
                expected_journal_pl = expected_pnl - 1.0
                assert entry.get("realized_pl") is not None
                assert abs(entry["realized_pl"] - expected_journal_pl) < 0.01
        finally:
            reset_journal_db_path()


def test_record_options_close_creates_journal_entry_with_contract_fields() -> None:
    """POST /journal/record-close creates journal entry with contract_key, expiry, strike, right, premium."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db, journal_list

    with __import__("tempfile").TemporaryDirectory() as tmp:
        set_journal_db_path(Path(tmp) / "journal.db")
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/journal/record-close",
                    json={
                        "symbol": "SPY",
                        "strategy": "CSP",
                        "action": "CLOSE_CSP",
                        "qty": 1,
                        "premium": 1.25,
                        "fees": 0.5,
                        "contract_key": "SPY250321P00450000",
                        "expiry": "2025-03-21",
                        "strike": 450,
                        "right": "P",
                        "notes": "R27.3 record-close test",
                        "trade_date": "2026-02-27",
                    },
                )
            assert r.status_code == 200
            data = r.json()
            raw = json.dumps(data)
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
            assert data.get("status") == "OK"
            entry = data.get("entry", {})
            assert entry.get("symbol") == "SPY"
            assert entry.get("strategy") == "CSP"
            assert entry.get("action") == "CLOSE_CSP"
            assert entry.get("contract_key") == "SPY250321P00450000"
            assert entry.get("expiry") == "2025-03-21"
            assert entry.get("strike") == 450
            assert entry.get("right") == "P"
            assert entry.get("premium") == 1.25
            assert entry.get("is_paper") == 0
            entries = journal_list(limit=10, include_paper=False)
            found = [e for e in entries if e.get("contract_key") == "SPY250321P00450000"]
            assert len(found) >= 1
        finally:
            reset_journal_db_path()


def test_shares_close_and_record_close_api_no_fail_warn_in_response() -> None:
    """API responses for shares close and journal record-close must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.accounts import holdings_db
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db

    with tempfile.TemporaryDirectory() as out_dir_str:
        out_dir = Path(out_dir_str)
        set_journal_db_path(out_dir / "journal.db")
        init_journal_db()
        try:
            with patch.object(holdings_db, "_db_path", return_value=out_dir / "account.db"):
                holdings_db.init_db()
                holdings_db.delete_share_position("default", "QQQ")
                holdings_db.upsert_share_position("default", "QQQ", 5, avg_cost=200.0)
                with patch("app.api.ui_routes._require_ui_key"):
                    client = TestClient(app)
                    r1 = client.post("/api/ui/shares/positions/QQQ/close", json={"account_id": "default", "exit_price": 205.0})
                    assert r1.status_code == 200
                    assert "FAIL_" not in json.dumps(r1.json())
                    assert "WARN_" not in json.dumps(r1.json())
                    r2 = client.post(
                        "/api/ui/journal/record-close",
                        json={"symbol": "SPY", "strategy": "CC", "action": "CLOSE_CC", "qty": 1},
                    )
                    assert r2.status_code == 200
                    assert "FAIL_" not in json.dumps(r2.json())
                    assert "WARN_" not in json.dumps(r2.json())
        finally:
            reset_journal_db_path()
