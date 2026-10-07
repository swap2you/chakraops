# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.5: Journal store + API — create, list, patch, export CSV, monthly report. Temp DB only."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def journal_temp_db():
    """Use a temp DB so we never write to data/journal.db during tests."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "journal.db"
        from app.core.journal import journal_store

        journal_store.set_journal_db_path(path)
        try:
            journal_store.init_journal_db()
            yield path
        finally:
            journal_store.reset_journal_db_path()


def test_journal_create_then_list_returns_it(journal_temp_db):
    """Create entry -> list returns it (ordered by created_ts desc)."""
    from app.core.journal.journal_store import journal_create, journal_list

    entry = journal_create(
        trade_date="2026-02-15",
        symbol="SPY",
        strategy="SHARES",
        action="BUY",
        qty=100.0,
        price=450.0,
        notes="test buy",
    )
    assert entry.get("id")
    assert entry.get("symbol") == "SPY"
    assert entry.get("trade_date") == "2026-02-15"
    assert entry.get("action") == "BUY"

    listed = journal_list(from_date="2026-02-01", to_date="2026-02-28")
    assert len(listed) == 1
    assert listed[0]["id"] == entry["id"]
    assert listed[0]["symbol"] == "SPY"


def test_journal_patch_notes_tags(journal_temp_db):
    """PATCH notes and tags updates the entry."""
    from app.core.journal.journal_store import journal_create, journal_get, journal_update

    entry = journal_create(
        trade_date="2026-02-16",
        symbol="QQQ",
        strategy="CSP",
        action="OPEN_CSP",
        qty=1.0,
        premium=2.50,
    )
    eid = entry["id"]
    updated = journal_update(eid, notes="updated note", tags="tag1,tag2")
    assert updated is not None
    assert updated["notes"] == "updated note"
    assert updated["tags"] == "tag1,tag2"
    got = journal_get(eid)
    assert got["notes"] == "updated note"
    assert got["tags"] == "tag1,tag2"


def test_journal_export_csv_header_and_row(journal_temp_db):
    """Export CSV returns header + at least one row when data exists."""
    from app.core.journal.journal_store import journal_create, journal_export_csv

    journal_create(
        trade_date="2026-02-17",
        symbol="IWM",
        strategy="SHARES",
        action="SELL",
        qty=50.0,
        price=210.0,
    )
    csv_str = journal_export_csv("2026-02-01", "2026-02-28")
    lines = [l.strip() for l in csv_str.strip().splitlines() if l.strip()]
    assert len(lines) >= 2
    header = lines[0].lower()
    assert "symbol" in header
    assert "trade_date" in header
    assert "strategy" in header
    # at least one data row
    assert "IWM" in csv_str or "iwm" in csv_str


def test_journal_monthly_aggregate_totals_and_order(journal_temp_db):
    """Monthly report: realized P/L totals, by strategy, winners/losers order."""
    from app.core.journal.journal_store import journal_create, journal_monthly_aggregate

    journal_create(
        trade_date="2026-02-10",
        symbol="A",
        strategy="SHARES",
        action="BUY",
        qty=100.0,
        price=100.0,
        realized_pl=50.0,
    )
    journal_create(
        trade_date="2026-02-11",
        symbol="B",
        strategy="CSP",
        action="CLOSE_CSP",
        qty=1.0,
        premium=-1.0,
        realized_pl=-20.0,
    )
    journal_create(
        trade_date="2026-02-12",
        symbol="C",
        strategy="CC",
        action="CLOSE_CC",
        qty=1.0,
        realized_pl=100.0,
    )
    report = journal_monthly_aggregate("2026-02")
    assert report["month"] == "2026-02"
    assert report["total_realized_pl"] == 130.0  # 50 - 20 + 100
    assert "SHARES" in report["by_strategy"]
    assert "CSP" in report["by_strategy"]
    assert "CC" in report["by_strategy"]
    assert report["trade_count"] == 3
    assert report["win_count"] == 2
    assert report["loss_count"] == 1
    # top_winners descending by realized_pl
    winners = report["top_winners"]
    assert len(winners) >= 2
    pls = [w.get("realized_pl") for w in winners if w.get("realized_pl") is not None]
    assert pls == sorted(pls, reverse=True)
    # top_losers ascending (worst first)
    losers = report["top_losers"]
    loser_pls = [l.get("realized_pl") for l in losers if l.get("realized_pl") is not None]
    assert loser_pls == sorted(loser_pls)


def test_journal_api_list_and_create_and_response_no_fail_warn(journal_temp_db):
    """API: GET list, POST create; response JSON must not contain FAIL_ or WARN_ (word boundary)."""
    from fastapi.testclient import TestClient

    from app.api.server import app

    client = TestClient(app)
    # List (empty)
    r = client.get("/api/ui/journal?from_date=2026-02-01&to_date=2026-02-28")
    assert r.status_code == 200
    text = r.text
    assert "entries" in r.json()
    assert re.search(r"\bFAIL(?:_|\b)", text) is None
    assert re.search(r"\bWARN(?:_|\b)", text) is None

    # Create
    r2 = client.post(
        "/api/ui/journal",
        json={
            "trade_date": "2026-02-20",
            "symbol": "TEST",
            "strategy": "SHARES",
            "action": "BUY",
            "qty": 10,
            "price": 100.0,
        },
    )
    assert r2.status_code == 200
    text2 = r2.text
    assert re.search(r"\bFAIL(?:_|\b)", text2) is None
    assert re.search(r"\bWARN(?:_|\b)", text2) is None
    data = r2.json()
    assert "entry" in data
    assert data["entry"]["symbol"] == "TEST"


def test_journal_api_monthly_report_no_fail_warn(journal_temp_db):
    """GET /api/ui/reports/monthly response must not contain FAIL_/WARN_."""
    from fastapi.testclient import TestClient

    from app.api.server import app

    client = TestClient(app)
    r = client.get("/api/ui/reports/monthly?month=2026-02")
    assert r.status_code == 200
    text = r.text
    assert re.search(r"\bFAIL(?:_|\b)", text) is None
    assert re.search(r"\bWARN(?:_|\b)", text) is None
    data = r.json()
    assert "month" in data
    assert "total_realized_pl" in data
    assert "top_winners" in data
    assert "top_losers" in data


def test_journal_api_export_csv_no_fail_warn(journal_temp_db):
    """POST export returns CSV; response body must not contain FAIL_/WARN_."""
    from app.core.journal.journal_store import journal_create
    from fastapi.testclient import TestClient

    from app.api.server import app

    journal_create(
        trade_date="2026-02-01",
        symbol="X",
        strategy="SHARES",
        action="BUY",
        qty=1,
        price=1.0,
    )
    client = TestClient(app)
    r = client.post("/api/ui/journal/export?from_date=2026-02-01&to_date=2026-02-28")
    assert r.status_code == 200
    text = r.text
    assert re.search(r"\bFAIL(?:_|\b)", text) is None
    assert re.search(r"\bWARN(?:_|\b)", text) is None
    assert "symbol" in text.lower() or "id" in text.lower()
