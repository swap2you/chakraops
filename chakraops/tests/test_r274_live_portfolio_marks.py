# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.4: Live portfolio mark/unrealized parity; journal link_target; no FAIL_/WARN_ in payloads."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def test_select_mark_order_deterministic() -> None:
    """Mark selection order: MID -> LAST -> BID -> ASK; centralized in position_lifecycle_r243."""
    from app.core.lifecycle.position_lifecycle_r243 import (
        select_mark_from_quote,
        MARK_SOURCE_MID,
        MARK_SOURCE_LAST,
        MARK_SOURCE_BID,
        MARK_SOURCE_ASK,
    )

    # MID when both bid and ask
    mark, src, _, _ = select_mark_from_quote(bid=100.0, ask=102.0, last=101.0)
    assert mark == 101.0
    assert src == MARK_SOURCE_MID

    # LAST when no bid/ask
    mark, src, _, _ = select_mark_from_quote(last=99.0)
    assert mark == 99.0
    assert src == MARK_SOURCE_LAST

    # BID then ASK
    mark, src, _, _ = select_mark_from_quote(bid=98.0)
    assert mark == 98.0
    assert src == MARK_SOURCE_BID
    mark, src, _, _ = select_mark_from_quote(ask=103.0)
    assert mark == 103.0
    assert src == MARK_SOURCE_ASK


def test_enrich_live_shares_missing_quote_nulls() -> None:
    """Missing quote -> mark_value, mark_source, quote_ts, mark_age_sec, unrealized_pl are null."""
    from app.core.portfolio.live_shares_mark_r274 import enrich_live_shares_positions_with_mark

    positions = [
        {"symbol": "SPY", "quantity": 10, "avg_cost": 100.0},
        {"symbol": "QQQ", "quantity": 5, "avg_cost": 200.0},
    ]
    price_by_symbol: dict[str, float] = {}
    out = enrich_live_shares_positions_with_mark(positions, price_by_symbol, None)
    assert len(out) == 2
    for p in out:
        assert p.get("mark_value") is None
        assert p.get("mark_source") is None
        assert p.get("quote_ts") is None
        assert p.get("mark_age_sec") is None
        assert p.get("unrealized_pl") is None


def test_enrich_live_shares_with_quote_sets_mark_and_unrealized_pl() -> None:
    """When price available, mark_value, mark_source, unrealized_pl are set."""
    from app.core.portfolio.live_shares_mark_r274 import enrich_live_shares_positions_with_mark

    positions = [{"symbol": "SPY", "quantity": 10, "avg_cost": 100.0}]
    out = enrich_live_shares_positions_with_mark(positions, {"SPY": 105.0}, None)
    assert len(out) == 1
    assert out[0]["mark_value"] == 105.0
    assert out[0]["mark_source"] == "LAST"
    assert out[0]["unrealized_pl"] == 50.0  # (105 - 100) * 10


def test_parse_link_id_formats() -> None:
    """link_id formats: shares:, paper:, options:record: -> { kind, id }."""
    from app.core.journal.journal_links_r274 import parse_link_id

    assert parse_link_id("shares:SPY:abc-uuid") == {"kind": "shares", "id": "SPY:abc-uuid"}
    assert parse_link_id("paper:pos-123") == {"kind": "paper", "id": "pos-123"}
    assert parse_link_id("options:record:SPY250321C00450000") == {"kind": "options", "id": "SPY250321C00450000"}
    assert parse_link_id("") is None
    assert parse_link_id(None) is None
    assert parse_link_id("unknown:format") is None


def test_portfolio_response_no_fail_warn_substrings() -> None:
    """GET /portfolio (and shares_positions) must not contain FAIL_ or WARN_ in JSON."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.eval.evaluation_store_v2 import set_output_dir, reset_output_dir

    with __import__("tempfile").TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        set_output_dir(out_dir)
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/portfolio")
            assert r.status_code == 200
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
        finally:
            reset_output_dir()


def test_journal_list_response_no_fail_warn_substrings() -> None:
    """GET /journal entries payload must not contain FAIL_ or WARN_ in JSON."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db

    with __import__("tempfile").TemporaryDirectory() as tmp:
        set_journal_db_path(Path(tmp) / "journal.db")
        init_journal_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/journal?limit=5")
            assert r.status_code == 200
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw
            assert "WARN_" not in raw
        finally:
            reset_journal_db_path()


def test_journal_list_includes_link_target_when_link_id_present() -> None:
    """GET /journal adds request-time link_target { kind, id } when link_id is recognized."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_create,
        journal_list,
    )

    with __import__("tempfile").TemporaryDirectory() as tmp:
        set_journal_db_path(Path(tmp) / "journal.db")
        init_journal_db()
        try:
            journal_create(
                trade_date="2026-02-20",
                symbol="SPY",
                strategy="SHARES",
                action="SELL",
                qty=100,
                price=450.0,
                link_id="shares:SPY:pos-abc",
            )
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/journal?limit=10")
            assert r.status_code == 200
            entries = r.json().get("entries") or []
            share_entry = next((e for e in entries if (e.get("link_id") or "").startswith("shares:")), None)
            assert share_entry is not None
            assert share_entry.get("link_target") == {"kind": "shares", "id": "SPY:pos-abc"}
        finally:
            reset_journal_db_path()
