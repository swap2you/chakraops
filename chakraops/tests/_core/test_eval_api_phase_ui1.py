# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase UI-1: API contract tests for /api/eval/latest-run, /api/eval/symbol/{symbol}, /api/system/health."""

from __future__ import annotations

from unittest.mock import patch

import pytest


def test_build_latest_run_response_no_runs():
    """When no runs exist, response has expected shape."""
    from app.api.eval_routes import build_latest_run_response

    with patch("app.api.eval_routes._get_latest_run", return_value=None):
        resp = build_latest_run_response()

    assert "run_id" in resp
    assert "as_of" in resp
    assert "status" in resp
    assert "duration_sec" in resp
    assert "symbols_evaluated" in resp
    assert "symbols_skipped" in resp
    assert "top_ranked" in resp
    assert "warnings" in resp
    assert "throughput" in resp
    assert resp["status"] == "NO_RUNS"
    assert resp["top_ranked"] == []
    assert "wall_time_sec" in resp["throughput"]


def test_build_symbol_response_no_run():
    """When no run, symbol response has error."""
    from app.api.eval_routes import build_symbol_response

    with patch("app.api.eval_routes._get_latest_run", return_value=None):
        resp = build_symbol_response("AAPL")

    assert resp["symbol"] == "AAPL"
    assert "error" in resp


def test_build_symbol_response_symbol_not_found():
    """When symbol not in run, response has error."""
    from app.api.eval_routes import build_symbol_response

    mock_run = {
        "symbols": [{"symbol": "SPY", "verdict": "HOLD"}],
    }

    with patch("app.api.eval_routes._get_latest_run", return_value=mock_run):
        resp = build_symbol_response("AAPL")

    assert resp["symbol"] == "AAPL"
    assert "error" in resp


def test_build_symbol_response_found():
    """When symbol in run, response has stage1, stage2, sizing, traces."""
    from app.api.eval_routes import build_symbol_response

    mock_run = {
        "symbols": [{
            "symbol": "AAPL",
            "verdict": "ELIGIBLE",
            "quote_date": "2026-02-10",
            "symbol_eligibility": {"status": "PASS", "required_data_missing": []},
            "contract_data": {},
            "contract_eligibility": {"status": "PASS"},
            "score": 80,
            "capital_hint": {"band": "A"},
        }],
    }

    with patch("app.api.eval_routes._get_latest_run", return_value=mock_run):
        resp = build_symbol_response("AAPL")

    assert resp["symbol"] == "AAPL"
    assert "stage1" in resp
    assert "stage2" in resp
    assert "sizing" in resp
    assert "traces" in resp
    assert resp["stage1"]["data_sufficiency"]["status"] == "PASS"
    assert resp["stage2"]["score"] == 80


def test_build_system_health_response_shape():
    """Response has expected shape (works with or without diagnostics file)."""
    from app.api.eval_routes import build_system_health_response

    resp = build_system_health_response()
    assert "run_id" in resp
    assert "watchdog" in resp
    assert "cache" in resp
    assert "budget" in resp
    assert "recent_run_ids" in resp
    assert "warnings" in resp["watchdog"]


def test_run_diagnostics_store_save_load(tmp_path):
    """save_run_diagnostics and load_run_diagnostics round-trip."""
    from app.core.eval.run_diagnostics_store import save_run_diagnostics, load_run_diagnostics

    with patch("app.core.eval.run_diagnostics_store._diagnostics_path", return_value=tmp_path / "diag.json"):
        save_run_diagnostics(
            "eval_123",
            wall_time_sec=60,
            requests_estimated=100,
            cache_hit_rate_pct=85.0,
        )
        loaded = load_run_diagnostics()

    assert loaded is not None
    assert loaded["run_id"] == "eval_123"
    assert loaded["wall_time_sec"] == 60
    assert loaded["requests_estimated"] == 100
    assert loaded["cache_hit_rate_pct"] == 85.0


def test_api_endpoints_contract():
    """GET /api/eval/latest-run, /api/eval/symbol/{s}, /api/system/health return 200 and expected keys."""
    try:
        from fastapi.testclient import TestClient
        from app.api.server import app
    except ImportError:
        pytest.skip("fastapi not installed")

    client = TestClient(app)

    r = client.get("/api/eval/latest-run")
    assert r.status_code == 200
    data = r.json()
    assert "run_id" in data
    assert "status" in data
    assert "top_ranked" in data
    assert "throughput" in data

    r = client.get("/api/eval/symbol/AAPL")
    assert r.status_code == 200
    data = r.json()
    assert "symbol" in data

    r = client.get("/api/system/health")
    assert r.status_code == 200
    data = r.json()
    assert "watchdog" in data
    assert "cache" in data
    assert "budget" in data
