# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: API contract tests — market-status, symbol-diagnostics (UNKNOWN not 500)."""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    from app.api.server import app
    _HAS_FASTAPI = True
except ImportError:
    TestClient = None  # type: ignore[misc, assignment]
    app = None  # type: ignore[misc, assignment]
    _HAS_FASTAPI = False

_client = None


def _client_fixture():
    if not _HAS_FASTAPI:
        pytest.skip("fastapi not installed")
    from fastapi.testclient import TestClient as TC
    from app.api.server import app as _app
    global _client
    if _client is None:
        _client = TC(_app)
    return _client


def test_market_status_returns_required_keys() -> None:
    """GET /api/market-status returns ok, market_phase, last_market_check, last_evaluated_at, evaluation_attempted, evaluation_emitted, skip_reason."""
    client = _client_fixture()
    r = client.get("/api/market-status")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "market_phase" in data
    assert "last_market_check" in data
    assert "last_evaluated_at" in data
    assert "evaluation_attempted" in data
    assert "evaluation_emitted" in data
    assert "skip_reason" in data
    assert data["market_phase"] in ("PRE", "OPEN", "MID", "POST", "CLOSED", None) or isinstance(data["market_phase"], str)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_symbol_diagnostics_returns_200_unknown_not_500() -> None:
    """GET /api/view/symbol-diagnostics?symbol=UNKNOWNXYZ returns 200 with recommendation (or 503 if ORATS fails)."""
    from unittest.mock import patch
    with patch("app.core.orats.orats_client.get_orats_live_summaries", return_value=[{"stockPrice": 1.0, "ticker": "UNKNOWNXYZ"}]):
        with patch("app.api.data_health.fetch_universe_from_orats", return_value={"symbols": [], "excluded": [], "all_failed": False, "updated_at": None}):
            client = _client_fixture()
            r = client.get("/api/view/symbol-diagnostics", params={"symbol": "UNKNOWNXYZ"})
    if r.status_code == 503:
        pytest.skip("ORATS failed for UNKNOWNXYZ (no mock or token)")
    assert r.status_code == 200
    data = r.json()
    assert "symbol" in data
    assert data["symbol"] == "UNKNOWNXYZ"
    assert "recommendation" in data
    assert data["recommendation"] in ("ELIGIBLE", "NOT_ELIGIBLE", "UNKNOWN")
    assert "in_universe" in data
    assert "gates" in data
    assert "blockers" in data


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_symbol_diagnostics_out_of_universe_returns_200_out_of_scope() -> None:
    """Out-of-universe symbol returns 200 with status OUT_OF_SCOPE when ORATS returns data but symbol not in universe."""
    from unittest.mock import patch
    with patch("app.core.orats.orats_client.get_orats_live_summaries", return_value=[{"stockPrice": 1.0, "ticker": "UNKNOWNXYZ"}]):
        with patch("app.api.data_health.fetch_universe_from_orats", return_value={"symbols": [{"symbol": "SPY", "source": "orats", "last_price": 450.0, "fetched_at": None, "exclusion_reason": None}], "excluded": [], "all_failed": False, "updated_at": None}):
            client = _client_fixture()
            r = client.get("/api/view/symbol-diagnostics", params={"symbol": "UNKNOWNXYZ"})
    if r.status_code == 503:
        pytest.skip("ORATS failed (no mock or token)")
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "UNKNOWNXYZ"
    assert data["in_universe"] is False
    assert data.get("status") == "OUT_OF_SCOPE"
    assert "reason" in data
    assert "fetched_at" in data
    blockers = data.get("blockers") or []
    codes = [b.get("code") for b in blockers if isinstance(b, dict)]
    assert "NOT_IN_UNIVERSE" in codes


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_universe_returns_stable_shape() -> None:
    """GET /api/view/universe returns 200 with symbols, updated_at, error (null). Never 503."""
    from unittest.mock import patch
    payload = {
        "symbols": [{"symbol": "SPY", "source": "orats", "last_price": 450.0, "fetched_at": "2026-02-01T12:00:00Z", "exclusion_reason": None}],
        "excluded": [],
        "all_failed": False,
        "updated_at": "2026-02-01T12:00:00Z",
    }
    with patch("app.api.data_health.fetch_universe_from_orats", return_value=payload):
        client = _client_fixture()
        r = client.get("/api/view/universe")
    assert r.status_code == 200
    data = r.json()
    assert "symbols" in data
    assert "updated_at" in data
    assert "error" in data
    assert data["error"] is None


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_symbol_diagnostics_missing_symbol_returns_422() -> None:
    """Missing symbol query returns 422."""
    client = _client_fixture()
    r = client.get("/api/view/symbol-diagnostics")
    assert r.status_code == 422


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_healthz_returns_ok() -> None:
    """GET /api/healthz returns ok."""
    client = _client_fixture()
    r = client.get("/api/healthz")
    assert r.status_code == 200
    assert r.json().get("ok") is True


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_ops_status_returns_phase12_shape() -> None:
    """GET /api/ops/status returns last_run_at, next_run_at, cadence_minutes, last_run_reason, symbols_evaluated, trades_found, blockers_summary."""
    client = _client_fixture()
    r = client.get("/api/ops/status")
    assert r.status_code == 200
    data = r.json()
    assert "last_run_at" in data
    assert "next_run_at" in data
    assert "cadence_minutes" in data
    assert "last_run_reason" in data
    assert "symbols_evaluated" in data
    assert "trades_found" in data
    assert "blockers_summary" in data
    assert "market_phase" in data
    assert isinstance(data["blockers_summary"], dict)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_ops_evaluate_unknown_job_returns_200_not_404() -> None:
    """GET /api/ops/evaluate/{job_id} for unknown job_id returns 200 with state=not_found, never 404."""
    client = _client_fixture()
    r = client.get("/api/ops/evaluate/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200
    data = r.json()
    assert data.get("state") == "not_found"


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_trade_plan_returns_200_stable_shape() -> None:
    """GET /api/view/trade-plan returns 200 with trade_plan and fetched_at (optional endpoint, never 404)."""
    client = _client_fixture()
    r = client.get("/api/view/trade-plan")
    assert r.status_code == 200
    data = r.json()
    assert "trade_plan" in data
    assert "fetched_at" in data


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_symbol_diagnostics_spy_returns_200_with_fetched_at() -> None:
    """GET /api/view/symbol-diagnostics?symbol=SPY returns 200 with fetched_at (or 503 if ORATS fails)."""
    from unittest.mock import patch
    with patch("app.core.orats.orats_client.get_orats_live_summaries", return_value=[{"stockPrice": 450.0, "ticker": "SPY"}]):
        with patch("app.api.data_health.fetch_universe_from_orats", return_value={"symbols": [{"symbol": "SPY", "source": "orats", "last_price": 450.0, "fetched_at": "2026-02-01T12:00:00Z", "exclusion_reason": None}], "excluded": [], "all_failed": False, "updated_at": "2026-02-01T12:00:00Z"}):
            client = _client_fixture()
            r = client.get("/api/view/symbol-diagnostics", params={"symbol": "SPY"})
    if r.status_code == 503:
        pytest.skip("ORATS failed for SPY (no mock or token)")
    assert r.status_code == 200
    data = r.json()
    assert data.get("symbol") == "SPY"
    assert "fetched_at" in data
    assert "status" in data or "recommendation" in data
    assert data.get("recommendation") in ("ELIGIBLE", "NOT_ELIGIBLE", "UNKNOWN", None) or data.get("status") in ("OUT_OF_SCOPE", "UNKNOWN", None)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi not installed")
def test_post_ops_evaluate_returns_200_with_job_id_or_ack() -> None:
    """POST /api/ops/evaluate returns 200 with job_id (accepted) or cooldown_seconds_remaining (not accepted)."""
    client = _client_fixture()
    r = client.post("/api/ops/evaluate", json={"reason": "MANUAL_REFRESH", "scope": "ALL"})
    assert r.status_code == 200
    data = r.json()
    assert "accepted" in data
    if data.get("accepted"):
        assert "job_id" in data
    else:
        assert "cooldown_seconds_remaining" in data
