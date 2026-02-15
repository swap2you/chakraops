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


# Phase UI-2 tests
def test_normalize_latest_run_has_score_final_verdict():
    """top_ranked rows have score and final_verdict when available."""
    from app.api.response_normalizers import normalize_latest_run

    payload = {
        "run_id": "x",
        "top_ranked": [
            {"symbol": "AAPL", "status": "ELIGIBLE", "score": 80},
            {"symbol": "SPY", "verdict": "HOLD", "composite_score": 50},
        ],
    }
    out = normalize_latest_run(payload)
    rows = out["top_ranked"]
    assert rows[0]["final_verdict"] == "ELIGIBLE"
    assert rows[0]["score"] == 80
    assert rows[1]["final_verdict"] == "HOLD"
    assert rows[1]["score"] == 50


def test_normalize_symbol_payload_selected_contract_shape():
    """Symbol payload has normalized selected_contract with strike, expiration, dte, delta, bid, ask."""
    from app.api.response_normalizers import normalize_symbol_payload

    payload = {
        "symbol": "AAPL",
        "stage2": {
            "candidate_contract": {"strike": 150, "expiration": "2026-03-20", "dte": 35, "delta": -0.25, "bid": 2.50},
        },
    }
    out = normalize_symbol_payload(payload)
    sc = out.get("stage2", {}).get("selected_contract") or {}
    assert "strike" in sc
    assert "expiration" in sc
    assert "dte" in sc
    assert "delta" in sc
    assert "bid" in sc
    assert sc.get("strike") == 150


def test_build_runs_response():
    """build_runs_response returns list with expected keys per run."""
    from app.api.eval_routes import build_runs_response
    from types import SimpleNamespace

    mock_summary = SimpleNamespace(
        run_id="eval_1",
        completed_at="2026-02-10T14:30:00",
        status="COMPLETED",
        duration_seconds=60,
        evaluated=10,
        eligible=2,
    )

    with patch("app.core.eval.evaluation_store.list_runs", return_value=[mock_summary]):
        resp = build_runs_response(limit=5)

    assert isinstance(resp, list)
    if resp:
        r = resp[0]
        assert "run_id" in r
        assert "as_of" in r
        assert "status" in r
        assert "duration_sec" in r
        assert "symbols_evaluated" in r
        assert "eligible_count" in r
        assert "warnings_count" in r


def test_api_eval_runs_endpoint():
    """GET /api/eval/runs returns list."""
    try:
        from fastapi.testclient import TestClient
        from app.api.server import app
    except ImportError:
        pytest.skip("fastapi not installed")

    client = TestClient(app)
    r = client.get("/api/eval/runs?limit=5")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


def test_api_export_endpoints():
    """Export endpoints return 200 with JSON or 404 when no data."""
    try:
        from fastapi.testclient import TestClient
        from app.api.server import app
    except ImportError:
        pytest.skip("fastapi not installed")

    client = TestClient(app)
    r = client.get("/api/eval/export/latest-run")
    if r.status_code == 200:
        assert "application/json" in r.headers.get("content-type", "")
    else:
        assert r.status_code == 404

    r = client.get("/api/eval/export/diagnostics")
    if r.status_code == 200:
        assert "application/json" in r.headers.get("content-type", "")
    else:
        assert r.status_code == 404
