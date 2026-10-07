# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for /api/view/universe source routing: LIVE_COMPUTE vs ARTIFACT_LATEST vs LIVE_COMPUTE_NO_ARTIFACT."""

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

pytestmark_api = pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")


@pytestmark_api
@patch("app.api.server.get_market_phase", return_value="OPEN")
@patch("app.api.data_health.fetch_universe_from_canonical_snapshot")
def test_universe_market_open_uses_compute_path(mock_fetch, _mock_phase):
    """When market is OPEN, universe uses live compute and returns source=LIVE_COMPUTE."""
    mock_fetch.return_value = {
        "symbols": [{"symbol": "SPY", "last_price": 500.0}],
        "excluded": [],
        "all_failed": False,
        "updated_at": "2026-02-10T12:00:00+00:00",
    }
    client = TestClient(app)
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "LIVE_COMPUTE"
    assert "symbols" in data
    mock_fetch.assert_called_once()


@pytestmark_api
@patch("app.api.server.get_market_phase", return_value="CLOSED")
@patch("app.core.eval.run_artifacts.build_universe_from_latest_artifact")
def test_universe_market_closed_artifacts_present_uses_artifact_path(mock_build_artifact, _mock_phase):
    """When market is not OPEN and latest artifact exists, universe uses artifact and returns source=ARTIFACT_LATEST."""
    mock_build_artifact.return_value = {
        "symbols": [
            {"symbol": "AAPL", "last_price": 175.0, "quote_as_of": "2026-02-10T20:00:00Z", "field_sources": {}},
        ],
        "excluded": [],
        "all_failed": False,
        "updated_at": "2026-02-10T20:00:00+00:00",
        "as_of": "2026-02-10T20:00:00+00:00",
        "run_id": "eval_20260210_200000_abc",
    }
    client = TestClient(app)
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "ARTIFACT_LATEST"
    assert data["run_id"] == "eval_20260210_200000_abc"
    assert data["as_of"] == "2026-02-10T20:00:00+00:00"
    assert len(data["symbols"]) == 1
    assert data["symbols"][0]["symbol"] == "AAPL"
    mock_build_artifact.assert_called_once()


@pytestmark_api
@patch("app.api.server.get_market_phase", return_value="POST")
@patch("app.core.eval.run_artifacts.build_universe_from_latest_artifact", return_value=None)
@patch("app.api.data_health.fetch_universe_from_canonical_snapshot")
def test_universe_market_closed_no_artifact_uses_compute_path(mock_fetch, _mock_artifact, _mock_phase):
    """When market is not OPEN and no artifact exists, universe falls back to live compute and returns source=LIVE_COMPUTE_NO_ARTIFACT."""
    mock_fetch.return_value = {
        "symbols": [{"symbol": "QQQ", "last_price": 450.0}],
        "excluded": [],
        "all_failed": False,
        "updated_at": "2026-02-10T21:00:00+00:00",
    }
    client = TestClient(app)
    r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "LIVE_COMPUTE_NO_ARTIFACT"
    assert "symbols" in data
    mock_fetch.assert_called_once()
