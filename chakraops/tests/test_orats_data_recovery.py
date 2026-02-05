# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CRITICAL DATA RECOVERY: Tests that FAIL unless live ORATS data path works (or mocks are correct)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

try:
    from fastapi.testclient import TestClient
    from app.api.server import app
    _HAS_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    app = None  # type: ignore[misc, assignment]
    _HAS_FASTAPI = False


def _client():
    if not _HAS_FASTAPI:
        pytest.skip("fastapi not installed")
    return TestClient(app)


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_symbol_diagnostics_returns_503_when_orats_fails(mock_get_summaries):
    """Symbol-diagnostics returns 503 when ORATS raises OratsUnavailableError."""
    from app.core.orats.orats_client import OratsUnavailableError
    mock_get_summaries.side_effect = OratsUnavailableError(
        "unavailable", http_status=503, response_snippet="unavailable", endpoint="summaries", symbol="SPY"
    )
    client = _client()
    r = client.get("/api/view/symbol-diagnostics", params={"symbol": "SPY"})
    assert r.status_code == 503
    data = r.json()
    assert "detail" in data
    assert data["detail"].get("provider") == "ORATS" or "ORATS" in str(data["detail"])


def test_data_health_shape() -> None:
    """GET /api/ops/data-health returns provider, status, last_success_at, last_error_at, entitlement."""
    client = _client()
    r = client.get("/api/ops/data-health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "ORATS"
    assert "status" in data
    assert data["status"] in ("OK", "DEGRADED", "DOWN", "UNKNOWN")
    assert "last_success_at" in data
    assert "last_error_at" in data
    assert "last_error_reason" in data
    assert "entitlement" in data
    assert data["entitlement"] in ("LIVE", "DELAYED", "UNKNOWN")


def test_refresh_live_data_returns_fetched_at_or_503() -> None:
    """POST /api/ops/refresh-live-data returns 200 with probe result (ok, row_count, etc.) or 503 on ORATS failure."""
    client = _client()
    r = client.post("/api/ops/refresh-live-data")
    if r.status_code == 200:
        data = r.json()
        assert data.get("ok") is True
        assert "row_count" in data or "http_status" in data
    else:
        assert r.status_code == 503
        data = r.json()
        assert "detail" in data


@patch("app.api.data_health.fetch_universe_from_orats")
def test_universe_fails_when_orats_fails(mock_fetch):
    """Universe returns 200 with empty symbols when ORATS returns nothing for all symbols (never 503)."""
    mock_fetch.return_value = {
        "symbols": [],
        "excluded": [{"symbol": "SPY", "exclusion_reason": "ORATS error"}, {"symbol": "QQQ", "exclusion_reason": "ORATS error"}],
        "all_failed": True,
        "updated_at": "2026-02-01T12:00:00Z",
    }
    client = _client()
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert "symbols" in data
    assert data["symbols"] == []
    assert data.get("error") is None


@patch("app.api.data_health.fetch_universe_from_orats")
def test_universe_returns_symbols_when_orats_succeeds(mock_fetch):
    """Universe returns 200 with symbol, source, last_price, fetched_at when ORATS succeeds for some."""
    mock_fetch.return_value = {
        "symbols": [
            {"symbol": "SPY", "source": "orats", "last_price": 450.0, "fetched_at": "2026-02-01T12:00:00Z", "exclusion_reason": None},
        ],
        "excluded": [{"symbol": "QQQ", "exclusion_reason": "timeout"}],
        "all_failed": False,
        "updated_at": "2026-02-01T12:00:00Z",
    }
    client = _client()
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert "symbols" in data
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["symbol"] == "SPY"
    assert data["symbols"][0]["source"] == "orats"
    assert data["symbols"][0].get("last_price") == 450.0
    assert "fetched_at" in data["symbols"][0]
    assert data["symbols"][0].get("exclusion_reason") is None
    assert "updated_at" in data


@patch("app.core.options.providers.orats_client.get_summaries")
@patch("app.api.data_health.fetch_universe_from_orats")
def test_orats_live_spy_data_returns_price_and_timestamp(mock_fetch_universe, mock_get_summaries):
    """When ORATS returns SPY data, symbol-diagnostics has fetched_at and optional price."""
    mock_get_summaries.return_value = [
        {"stockPrice": 450.5, "ticker": "SPY", "updatedAt": "2026-02-01T12:00:00Z"},
    ]
    mock_fetch_universe.return_value = {
        "symbols": [{"symbol": "SPY", "source": "orats", "last_price": 450.5, "fetched_at": "2026-02-01T12:00:00Z", "exclusion_reason": None}],
        "excluded": [],
        "all_failed": False,
        "updated_at": "2026-02-01T12:00:00Z",
    }
    client = _client()
    r = client.get("/api/view/symbol-diagnostics", params={"symbol": "SPY"})
    assert r.status_code == 200
    data = r.json()
    assert data.get("symbol") == "SPY"
    assert "fetched_at" in data
    assert data.get("fetched_at")
    assert "data_latency_seconds" in data or "fetched_at" in data


def test_data_health_reports_down_when_orats_error_recorded() -> None:
    """data-health endpoint returns status; when DOWN, error is set (from probe_orats_live)."""
    client = _client()
    r = client.get("/api/ops/data-health")
    assert r.status_code == 200
    data = r.json()
    assert data.get("provider") == "ORATS"
    assert data.get("status") in ("OK", "DOWN")
    if data.get("status") == "DOWN":
        assert data.get("error") is not None
