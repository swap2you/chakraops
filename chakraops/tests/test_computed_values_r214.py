# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R21.4: Unit tests for computed_values (request-time only; not persisted)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_build_computed_values_at_request_time_deterministic():
    """_build_computed_values_at_request_time returns expected keys and values for fixed inputs."""
    from app.api.ui_routes import _build_computed_values_at_request_time

    technicals = {
        "rsi": 54.1,
        "atr": 2.5,
        "atr_pct": 0.02,
        "support_level": 100.0,
        "resistance_level": 110.0,
    }
    regime = "UP"
    sample_rej = [{"observed_delta_decimal_abs": 0.3}, {"observed_delta_decimal_abs": 0.5}]

    out = _build_computed_values_at_request_time(technicals, regime, sample_rej)

    assert "rsi" in out and out["rsi"] == 54.1
    assert "rsi_range" in out and isinstance(out["rsi_range"], list) and len(out["rsi_range"]) == 2
    assert "atr" in out and out["atr"] == 2.5
    assert "atr_pct" in out and out["atr_pct"] == 0.02
    assert "support_level" in out and out["support_level"] == 100.0
    assert "resistance_level" in out and out["resistance_level"] == 110.0
    assert "regime" in out and out["regime"] == "UP"
    assert "delta_band" in out and isinstance(out["delta_band"], list) and len(out["delta_band"]) == 2
    assert "rejected_count" in out and out["rejected_count"] == 2


def test_build_computed_values_missing_technicals():
    """When technicals are empty, numeric values are None; ranges and rejected_count still present."""
    from app.api.ui_routes import _build_computed_values_at_request_time

    out = _build_computed_values_at_request_time({}, None, [])

    assert out.get("rsi") is None
    assert out.get("atr") is None
    assert "rsi_range" in out and len(out["rsi_range"]) == 2
    assert "delta_band" in out and len(out["delta_band"]) == 2
    assert out["rejected_count"] == 0


def test_symbol_diagnostics_response_includes_computed_values(tmp_path):
    """GET /api/ui/symbol-diagnostics response includes computed_values with expected keys."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.core.eval.decision_artifact_v2 import SymbolDiagnosticsDetails, SymbolEvalSummary
    from app.core.eval.evaluation_store_v2 import set_output_dir

    set_output_dir(Path(tmp_path))
    technicals = {"rsi": 48.0, "atr": 1.2, "atr_pct": 0.015, "support_level": 95.0, "resistance_level": 105.0}
    summary = SymbolEvalSummary(
        symbol="NVDA",
        verdict="HOLD",
        final_verdict="HOLD",
        score=60,
        band="B",
        primary_reason="OK",
        stage_status="STAGE2_CHAIN",
        stage1_status="PASS",
        stage2_status="PASS",
        provider_status="OK",
        data_freshness=None,
        evaluated_at=None,
        strategy="CSP",
        price=100.0,
        expiration=None,
        has_candidates=True,
        candidate_count=1,
    )
    diagnostics_details = SymbolDiagnosticsDetails(
        technicals=technicals,
        exit_plan={"t1": 98, "t2": 96, "t3": 94, "stop": 92, "status": "AVAILABLE", "reason": None},
        risk_flags={},
        explanation={},
        stock={"price": 100.0},
        symbol_eligibility={"status": "PASS", "reasons": []},
        liquidity={},
        regime="UP",
        sample_rejected_due_to_delta=[],
    )
    mock_store = MagicMock()
    mock_store.get_symbol.return_value = (summary, [], [], None, diagnostics_details)
    mock_store.get_latest.return_value = None

    from app.api.server import app

    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=mock_store):
        client = TestClient(app)
        r = client.get("/api/ui/symbol-diagnostics?symbol=NVDA")
    assert r.status_code == 200
    data = r.json()
    cv = data.get("computed_values")
    assert cv is not None
    assert cv.get("rsi") == 48.0
    assert cv.get("regime") == "UP"
    assert "rsi_range" in cv and "delta_band" in cv and "rejected_count" in cv
