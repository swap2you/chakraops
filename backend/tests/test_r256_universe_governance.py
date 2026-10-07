# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.6: Universe governance — deterministic overlay write, audit store, propose/apply, API no FAIL/WARN."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_overlay():
    """Temporary overlay file (out/universe_overrides.json)."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "universe_overrides.json"
        path.write_text(json.dumps({"added": [], "removed": [], "updated_at": ""}), encoding="utf-8")
        yield path


@pytest.fixture
def temp_admin_db():
    """Temporary universe admin DB."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "universe_admin.db"
        from app.core.universe import universe_admin_store
        universe_admin_store.set_universe_admin_db_path(path)
        try:
            universe_admin_store.init_universe_admin_db()
            yield path
        finally:
            universe_admin_store.reset_universe_admin_db_path()


def test_deterministic_overlay_write(temp_overlay):
    """Same input -> same file bytes (sorted added/removed)."""
    from app.core.universe.universe_overrides import add_symbol, remove_symbol, _load_overlay
    with patch("app.core.universe.universe_overrides._overlay_path", return_value=temp_overlay):
        add_symbol("ZZZ")
        add_symbol("AAA")
        add_symbol("MMM")
        remove_symbol("CCC")
        raw1 = temp_overlay.read_text(encoding="utf-8")
        overlay1 = json.loads(raw1)
        assert overlay1["added"] == ["AAA", "MMM", "ZZZ"]
        assert "CCC" in overlay1["removed"]
        # Reload and save again (e.g. another add) and check order
        add_symbol("BBB")
        raw2 = temp_overlay.read_text(encoding="utf-8")
        overlay2 = json.loads(raw2)
        assert overlay2["added"] == ["AAA", "BBB", "MMM", "ZZZ"]


def test_propose_apply_audit_trail(temp_admin_db):
    """Propose add -> list returns it; apply -> overlay updated and log has APPLY_*."""
    from app.core.universe.universe_admin_store import create_proposal, list_history, get_proposal, mark_applied, log_apply
    prop = create_proposal("PROPOSE_ADD", "TEST", notes="test note")
    assert prop["symbol"] == "TEST"
    assert prop["status"] == "OPEN"
    hist = list_history(limit=5)
    assert len(hist) >= 1
    assert hist[0]["symbol"] == "TEST"
    got = get_proposal(prop["id"])
    assert got and got["status"] == "OPEN"
    mark_applied(prop["id"])
    log_apply("APPLY_ADD", "TEST")
    hist2 = list_history(limit=10)
    apply_entries = [h for h in hist2 if h["action"] == "APPLY_ADD" and h["symbol"] == "TEST"]
    assert len(apply_entries) >= 1


def test_apply_add_updates_overlay(temp_overlay, temp_admin_db):
    """Apply add -> overlay contains symbol; effective list includes it."""
    from app.core.universe.universe_overrides import add_symbol, get_effective_symbols
    from app.core.universe.universe_admin_store import log_apply
    base = ["AAPL", "MSFT"]
    with patch("app.core.universe.universe_overrides._overlay_path", return_value=temp_overlay):
        add_symbol("NEWTICK")
        log_apply("APPLY_ADD", "NEWTICK")
        effective = get_effective_symbols(base)
        assert "NEWTICK" in effective
        assert effective == sorted(effective)


def test_apply_remove_updates_overlay(temp_overlay, temp_admin_db):
    """Apply remove -> symbol in overlay.removed; effective list excludes it."""
    from app.core.universe.universe_overrides import remove_symbol, get_effective_symbols, _load_overlay
    from app.core.universe.universe_admin_store import log_apply
    with patch("app.core.universe.universe_overrides._overlay_path", return_value=temp_overlay):
        remove_symbol("AAPL")
        log_apply("APPLY_REMOVE", "AAPL")
        effective = get_effective_symbols(["AAPL", "MSFT"])
        assert "AAPL" not in effective
        assert "MSFT" in effective


def test_api_universe_admin_no_fail_warn(temp_overlay, temp_admin_db):
    """GET /api/ui/universe/admin response must not contain FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    with patch("app.api.data_health.get_base_universe_symbols", return_value=["AAPL", "MSFT"]):
        with patch("app.core.universe.universe_overrides._overlay_path", return_value=temp_overlay):
            client = TestClient(app)
            r = client.get("/api/ui/universe/admin?limit=10")
    assert r.status_code == 200
    text = r.text
    assert re.search(r"\bFAIL(?:_|\b)", text) is None
    assert re.search(r"\bWARN(?:_|\b)", text) is None
    data = r.json()
    assert "symbols" in data
    assert "history" in data


def test_api_universe_health_no_fail_warn(temp_overlay, temp_admin_db):
    """GET /api/ui/universe/health response must not contain FAIL_/WARN_."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    with patch("app.api.data_health.get_base_universe_symbols", return_value=["AAPL"]):
        with patch("app.core.universe.universe_overrides._overlay_path", return_value=temp_overlay):
            client = TestClient(app)
            r = client.get("/api/ui/universe/health")
    assert r.status_code == 200
    text = r.text
    assert re.search(r"\bFAIL(?:_|\b)", text) is None
    assert re.search(r"\bWARN(?:_|\b)", text) is None
    data = r.json()
    assert "total_symbols" in data
    assert "recently_added" in data
    assert "recently_removed" in data
