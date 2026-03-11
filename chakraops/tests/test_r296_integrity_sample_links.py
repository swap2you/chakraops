# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.6: Integrity sample items include safe deep links (positions + diagnostics); no decision write; deterministic."""

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
    """Patch decision store path so state file and decision_latest live under tmp_path."""
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m_decision:
        m_decision.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def _reconcile_with_sample_items(include_paper: bool, symbol=None, limit=50):
    """Fake reconcile that returns sample items with symbol/id for link tests."""
    items = [
        {"symbol": "AAPL", "instrument_type": "equity", "id": "1", "kind": "missing"},
        {"symbol": "MSFT", "instrument_type": "equity", "id": "2", "kind": "extra"},
    ]
    return {
        "status": "Review",
        "status_label": "Counts differ",
        "missing_count": 1,
        "extra_count": 1,
        "mismatched_count": 0,
        "items": items,
    }


def test_links_present_and_deterministic(positions_db_override, out_dir_override) -> None:
    """Run integrity check with fixture sample items; each item has link_positions_url and link_diagnostics_url; ordering unchanged."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import (
        get_reconcile_diff,
        get_positions_unified_rebuild_health,
    )

    with patch("app.core.portfolio.positions_unified_store_r279.get_reconcile_diff", side_effect=_reconcile_with_sample_items), \
         patch("app.core.portfolio.positions_unified_store_r279.get_positions_unified_rebuild_health") as m_rebuild:
        m_rebuild.return_value = {"finished_at_utc": "2026-01-01T12:00:00+00:00"}
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 200
    data = r.json()
    sample = data.get("sample_items") or []
    assert len(sample) >= 2
    for item in sample:
        assert "link_positions_url" in item
        assert "link_diagnostics_url" in item
        url = item["link_positions_url"]
        assert url.startswith("/positions?source=db&symbol=")
        assert "&include_paper=" in url
        assert item["link_diagnostics_url"] == "/system"
    # Deterministic order: (symbol, instrument_type, id) -> AAPL before MSFT
    symbols = [it.get("symbol") for it in sample]
    assert symbols == sorted(symbols)
    # Encoding: symbol in URL should be safe (e.g. AAPL and MSFT)
    assert "symbol=AAPL" in sample[0]["link_positions_url"] or "symbol=AAPL" in sample[1]["link_positions_url"]
    assert "include_paper=true" in sample[0]["link_positions_url"]


def test_links_safe_no_forbidden_tokens(positions_db_override, out_dir_override) -> None:
    """Sample item dict JSON has no whole-word FAIL/WARN/PASS and no FAIL_/WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import get_positions_unified_rebuild_health

    with patch("app.core.portfolio.positions_unified_store_r279.get_reconcile_diff", side_effect=_reconcile_with_sample_items), \
         patch("app.core.portfolio.positions_unified_store_r279.get_positions_unified_rebuild_health") as m_rebuild:
        m_rebuild.return_value = {"finished_at_utc": "2026-01-01T12:00:00+00:00"}
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": False},
            headers={"content-type": "application/json"},
        )
    assert r.status_code == 200
    data = r.json()
    raw = json.dumps(data, default=str)
    assert not FORBIDDEN.search(raw), "Response contained forbidden whole-word token"
    assert not FORBIDDEN_UNDERSCORE.search(raw), "Response contained FAIL_/WARN_"
    for item in data.get("sample_items") or []:
        item_raw = json.dumps(item, default=str)
        assert not FORBIDDEN.search(item_raw)
        assert not FORBIDDEN_UNDERSCORE.search(item_raw)


def test_integrity_links_do_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """GET and POST integrity-check do not create or modify out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import get_reconcile_diff, get_positions_unified_rebuild_health

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path), \
         patch("app.core.portfolio.positions_unified_store_r279.get_reconcile_diff", side_effect=_reconcile_with_sample_items), \
         patch("app.core.portfolio.positions_unified_store_r279.get_positions_unified_rebuild_health") as m_rebuild:
        m_rebuild.return_value = {"finished_at_utc": "2026-01-01T12:00:00+00:00"}
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/positions/unified/integrity-check")
        assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'
        client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_state_and_health_include_links(positions_db_override, out_dir_override) -> None:
    """State file and get_positions_unified_integrity_check_health last_sample_items include link fields."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import (
        get_positions_unified_rebuild_health,
        _integrity_check_state_path,
        load_integrity_check_state,
        get_positions_unified_integrity_check_health,
    )

    with patch("app.core.portfolio.positions_unified_store_r279.get_reconcile_diff", side_effect=_reconcile_with_sample_items), \
         patch("app.core.portfolio.positions_unified_store_r279.get_positions_unified_rebuild_health") as m_rebuild, \
         patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=out_dir_override / "decision_latest.json"):
        m_rebuild.return_value = {"finished_at_utc": "2026-01-01T12:00:00+00:00"}
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
        state_path = _integrity_check_state_path()
        assert state_path.exists()
        state = load_integrity_check_state()
        assert state is not None
        last = state.get("last")
        assert isinstance(last, dict)
        sample = last.get("sample_items") or []
        for item in sample:
            assert "link_positions_url" in item
            assert "link_diagnostics_url" in item
        health = get_positions_unified_integrity_check_health()
        last_sample = health.get("last_sample_items") or []
        for item in last_sample:
            assert "link_positions_url" in item
            assert "link_diagnostics_url" in item
