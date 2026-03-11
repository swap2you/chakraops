# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R29.4: Integrity check GET + state/history — safe labels only, no decision write, deterministic ordering."""

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
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path") as m:
        m.return_value = tmp_path / "decision_latest.json"
        yield tmp_path


def test_get_integrity_check_returns_only_safe_labels(positions_db_override, out_dir_override) -> None:
    """GET /api/ui/positions/unified/integrity-check response contains no FAIL/WARN/PASS or FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r = client.get("/api/ui/positions/unified/integrity-check")
    assert r.status_code == 200
    data = r.json()
    raw = json.dumps(data, default=str)
    assert not FORBIDDEN.search(raw), f"Response contained forbidden token: {raw}"
    assert not FORBIDDEN_UNDERSCORE.search(raw), f"Response contained FAIL_/WARN_: {raw}"
    assert "status" in data
    assert "last" in data
    assert "history" in data


def test_get_integrity_check_does_not_write_decision_latest(positions_db_override, tmp_path) -> None:
    """GET integrity-check does not write out/decision_latest.json."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text('{"pre": "existing"}', encoding="utf-8")
    with patch("app.core.eval.evaluation_store_v2.get_decision_store_path", return_value=decision_path), \
         patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.get("/api/ui/positions/unified/integrity-check")
    assert decision_path.read_text(encoding="utf-8").strip() == '{"pre": "existing"}'


def test_get_integrity_check_deterministic_ordering(positions_db_override, out_dir_override) -> None:
    """GET returns stable shape; history is list; last and history entries have consistent structure."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        r1 = client.get("/api/ui/positions/unified/integrity-check")
        r2 = client.get("/api/ui/positions/unified/integrity-check")
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    assert set(d1.keys()) == set(d2.keys())
    assert isinstance(d1.get("history"), list)
    assert isinstance(d2.get("history"), list)
    last1, last2 = d1.get("last"), d2.get("last")
    if last1 and last2 and last1.get("sample_items") and last2.get("sample_items"):
        s1 = [ (x.get("symbol"), x.get("instrument_type"), x.get("id")) for x in last1["sample_items"] ]
        s2 = [ (x.get("symbol"), x.get("instrument_type"), x.get("id")) for x in last2["sample_items"] ]
        assert s1 == s2


def test_state_file_safe_fields_only(positions_db_override, out_dir_override) -> None:
    """After POST run, state file (if written) contains only safe fields and no forbidden tokens."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.portfolio.positions_unified_store_r279 import _integrity_check_state_path, load_integrity_check_state

    with patch("app.core.accounts.holdings_db.list_share_positions", return_value=[]), \
         patch("app.core.accounts.holdings_db.list_closed_share_positions", return_value=[]), \
         patch("app.core.positions.store.list_positions", return_value=[]), \
         patch("app.core.paper.paper_store_r270.paper_list_positions", return_value=[]):
        client = TestClient(app)
        client.headers["x-ui-key"] = "test-ui-key"
        client.post(
            "/api/ui/positions/unified/integrity-check",
            json={"include_paper": True},
            headers={"content-type": "application/json"},
        )
    state_path = _integrity_check_state_path()
    if not state_path.exists():
        return
    raw = state_path.read_text(encoding="utf-8")
    assert not FORBIDDEN.search(raw)
    assert not FORBIDDEN_UNDERSCORE.search(raw)
    state = load_integrity_check_state()
    assert state is not None
    if isinstance(state.get("last"), dict):
        last = state["last"]
        assert last.get("status") in ("OK", "Review", None) or last.get("status") == "OK"
    if isinstance(state.get("history"), list):
        for entry in state["history"]:
            if isinstance(entry, dict) and isinstance(entry.get("sample_items"), list):
                for item in entry["sample_items"]:
                    if isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str) and (FORBIDDEN.search(v) or FORBIDDEN_UNDERSCORE.search(v)):
                                pytest.fail(f"State file sample item contained forbidden token: {item}")
