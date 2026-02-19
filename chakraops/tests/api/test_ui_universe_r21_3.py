# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.3: API tests for /api/ui/universe/symbols (add/remove overlay)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def temp_overlay(tmp_path):
    """Isolate overlay file to tmp_path."""
    overlay_file = tmp_path / "universe_overrides.json"
    with patch("app.core.universe.universe_overrides._overlay_path", return_value=overlay_file):
        yield overlay_file


@pytest.fixture
def temp_overlay_and_base(temp_overlay):
    """Also patch get_base_universe_symbols so GET /universe/symbols returns controlled base."""
    with patch("app.api.data_health.get_base_universe_symbols", return_value=["AAPL", "MSFT", "GOOGL"]):
        with patch("app.api.data_health.UNIVERSE_SYMBOLS", ["AAPL", "MSFT", "GOOGL"]):
            yield temp_overlay


def _client():
    from fastapi.testclient import TestClient
    from app.api.server import app
    return TestClient(app)


def test_get_universe_symbols_returns_structure(temp_overlay_and_base):
    """GET /api/ui/universe/symbols returns base_count, overlay_added_count, overlay_removed_count, symbols."""
    client = _client()
    r = client.get("/api/ui/universe/symbols")
    assert r.status_code == 200
    data = r.json()
    assert "base_count" in data
    assert "overlay_added_count" in data
    assert "overlay_removed_count" in data
    assert "symbols" in data
    assert data["base_count"] == 3
    assert data["symbols"] == ["AAPL", "GOOGL", "MSFT"]


def test_post_add_symbol_appears_in_get(temp_overlay_and_base):
    """POST add valid symbol -> appears in GET."""
    client = _client()
    r = client.post("/api/ui/universe/symbols", json={"symbol": "NVDA"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("symbol") == "NVDA"
    assert "NVDA" in body.get("symbols", [])

    r2 = client.get("/api/ui/universe/symbols")
    assert r2.status_code == 200
    assert "NVDA" in r2.json().get("symbols", [])
    assert r2.json().get("overlay_added_count") == 1


def test_delete_remove_symbol_disappears_from_get(temp_overlay_and_base):
    """DELETE remove symbol -> disappears from GET."""
    client = _client()
    client.post("/api/ui/universe/symbols", json={"symbol": "AMZN"})
    r = client.delete("/api/ui/universe/symbols/AAPL")
    assert r.status_code == 200
    assert "AAPL" not in r.json().get("symbols", [])

    r2 = client.get("/api/ui/universe/symbols")
    assert "AAPL" not in r2.json().get("symbols", [])
    assert r2.json().get("overlay_removed_count") == 1


def test_post_add_validation_rejects_invalid(temp_overlay_and_base):
    """POST with invalid symbol returns 400."""
    client = _client()
    for bad in ["", "TOOLONG12345", "bad!", "SP ACE"]:
        r = client.post("/api/ui/universe/symbols", json={"symbol": bad})
        assert r.status_code == 400, f"Expected 400 for {bad!r}"


def test_post_add_duplicate_idempotent(temp_overlay_and_base):
    """Adding same symbol twice is idempotent (still one in list)."""
    client = _client()
    client.post("/api/ui/universe/symbols", json={"symbol": "NVDA"})
    r2 = client.post("/api/ui/universe/symbols", json={"symbol": "NVDA"})
    assert r2.status_code == 200
    symbols = r2.json().get("symbols", [])
    assert symbols.count("NVDA") == 1


def test_remove_then_add_flips_correctly(temp_overlay_and_base):
    """Remove then add same symbol -> symbol back in list."""
    client = _client()
    client.delete("/api/ui/universe/symbols/MSFT")
    r1 = client.get("/api/ui/universe/symbols")
    assert "MSFT" not in r1.json().get("symbols", [])

    client.post("/api/ui/universe/symbols", json={"symbol": "MSFT"})
    r2 = client.get("/api/ui/universe/symbols")
    assert "MSFT" in r2.json().get("symbols", [])


def test_post_reset_clears_overlay(temp_overlay_and_base):
    """POST /universe/reset clears overlay."""
    client = _client()
    client.post("/api/ui/universe/symbols", json={"symbol": "NVDA"})
    client.delete("/api/ui/universe/symbols/AAPL")
    r = client.post("/api/ui/universe/reset")
    assert r.status_code == 200
    assert r.json().get("reset") is True
    symbols = r.json().get("symbols", [])
    assert "AAPL" in symbols
    assert "NVDA" not in symbols
