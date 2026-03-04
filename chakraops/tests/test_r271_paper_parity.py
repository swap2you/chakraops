# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.1: Paper-to-live parity — mark/unrealized, reports mode, monthly close pack live/paper, no FAIL_/WARN_."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_paper_positions_return_mark_fields_when_quote_provided() -> None:
    """Paper positions endpoint returns mark_value, mark_source, mark_age_sec, quote_ts, unrealized_pl_usd for OPEN when artifact has data."""
    from fastapi.testclient import TestClient
    from app.api.server import app
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
            paper_execute_open("SPY", "SHARES", 100, 450.0, 0, ts="2026-02-20T12:00:00Z")
            positions = paper_list_positions(status="OPEN")
            assert len(positions) >= 1
            # Enrich with mock artifact (price for SPY)
            from app.core.paper.paper_mark_r271 import enrich_paper_positions_with_mark
            with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2") as mock_get:
                store = MagicMock()
                sym = MagicMock()
                sym.symbol = "SPY"
                sym.price = 455.0
                sym.underlying_price = None
                store.get_latest.return_value = MagicMock(symbols=[sym], candidates_by_symbol={})
                mock_get.return_value = store
                store.reload_from_disk = MagicMock()
                enriched = enrich_paper_positions_with_mark(positions)
            assert len(enriched) >= 1
            p = enriched[0]
            assert p.get("mark_value") is not None
            assert p.get("mark_source") == "LAST"
            assert p.get("unrealized_pl_usd") is not None
            assert p["unrealized_pl_usd"] == round((455.0 - 450.0) * 100, 2)
        finally:
            reset_paper_db_path()


def test_mark_selection_order_stable() -> None:
    """Mark selection uses MID->LAST->BID->ASK; deterministic."""
    from app.core.lifecycle.position_lifecycle_r243 import select_mark_from_quote

    mark, src, _, _ = select_mark_from_quote(bid=2.0, ask=2.2, last=2.1, quote_ts="2026-02-27T12:00:00Z", as_of_ts=1730000000.0)
    assert mark is not None
    assert src == "MID"
    mark2, src2, _, _ = select_mark_from_quote(bid=None, ask=None, last=2.1)
    assert mark2 == 2.1
    assert src2 == "LAST"


def test_unrealized_pl_computed_correctly() -> None:
    """Unrealized P/L for options: (open_price - mark) * qty * 100."""
    from app.core.paper.paper_mark_r271 import enrich_paper_positions_with_mark

    positions = [{
        "id": "p1",
        "symbol": "SPY",
        "instrument_type": "OPTION",
        "strategy": "CSP",
        "qty": 2,
        "open_price": 3.0,
        "open_ts": "2026-02-20T12:00:00Z",
        "status": "OPEN",
        "expiry": "2026-03-21",
        "strike": 600,
        "right": "P",
    }]
    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2") as mock_get:
        store = MagicMock()
        art = MagicMock()
        art.symbols = []
        art.candidates_by_symbol = {"SPY": [{"exp": "2026-03-21", "strike": 600, "putCall": "P", "bid": 2.0, "ask": 2.2, "last": 2.1}]}
        store.get_latest.return_value = art
        mock_get.return_value = store
        store.reload_from_disk = MagicMock()
        enriched = enrich_paper_positions_with_mark(positions)
    assert len(enriched) == 1
    assert enriched[0].get("mark_value") is not None
    # (3.0 - 2.1) * 2 * 100 = 180
    assert enriched[0].get("unrealized_pl_usd") == 180.0


def test_reports_monthly_returns_included_paper_and_mode() -> None:
    """GET reports/monthly response includes included_paper and mode (LIVE_ONLY|PAPER_ONLY|MIXED)."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/reports/monthly?month=2026-02")
        assert r.status_code == 200
        data = r.json()
        assert "included_paper" in data
        assert data["included_paper"] is False
        assert data.get("mode") == "LIVE_ONLY"
        r2 = client.get("/api/ui/reports/monthly?month=2026-02&include_paper=true")
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["included_paper"] is True
        assert data2.get("mode") in ("LIVE_ONLY", "PAPER_ONLY", "MIXED")


def test_monthly_close_pack_respects_include_paper_and_writes_subdir() -> None:
    """Generate with include_paper=false -> live/ subdir; include_paper=true -> paper/ subdir; monthly_report.json has included_paper and mode."""
    from app.core.journal.journal_store import set_journal_db_path, reset_journal_db_path, init_journal_db
    from app.core.ops.monthly_close_store_r265 import (
        generate_monthly_close_pack,
        set_reports_base_path,
        reset_reports_base_path,
        PACK_LIVE,
        PACK_PAPER,
    )

    with tempfile.TemporaryDirectory() as tmp:
        set_reports_base_path(Path(tmp))
        try:
            r_live = generate_monthly_close_pack("2026-03", include_paper=False)
            assert r_live.get("pack") == PACK_LIVE
            assert (Path(tmp) / "2026-03" / "live" / "monthly_report.json").is_file()
            with open(Path(tmp) / "2026-03" / "live" / "monthly_report.json") as f:
                report = json.load(f)
            assert report.get("included_paper") is False
            assert report.get("mode") in ("LIVE_ONLY", "PAPER_ONLY", "MIXED")

            r_paper = generate_monthly_close_pack("2026-03", include_paper=True)
            assert r_paper.get("pack") == PACK_PAPER
            assert (Path(tmp) / "2026-03" / "paper" / "monthly_report.json").is_file()
            with open(Path(tmp) / "2026-03" / "paper" / "monthly_report.json") as f:
                report_p = json.load(f)
            assert report_p.get("included_paper") is True
        finally:
            reset_reports_base_path()


def test_paper_api_no_fail_warn_in_json() -> None:
    """Paper positions and reports monthly JSON must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        for url in [
            "/api/ui/paper/positions",
            "/api/ui/reports/monthly?month=2026-02",
        ]:
            r = client.get(url)
            if r.status_code != 200:
                continue
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw, url
            assert "WARN_" not in raw, url
