# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Delta rejection sample wiring: when rejected_due_to_delta > 0, diagnostics API includes sample and sample-driven message."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_symbol_diagnostics_includes_delta_sample_and_sample_driven_message(tmp_path):
    """When store has primary_reason with rejected_due_to_delta and diagnostics has sample_rejected_due_to_delta, API returns reasons_explained with sample-driven message (not generic)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.core.eval.decision_artifact_v2 import SymbolDiagnosticsDetails, SymbolEvalSummary
    from app.core.eval.evaluation_store_v2 import set_output_dir

    set_output_dir(Path(tmp_path))
    sample = [
        {
            "observed_delta_decimal_raw": -0.55,
            "observed_delta_decimal_abs": 0.55,
            "observed_delta_pct_abs": 55,
            "target_range_decimal": "0.20-0.40",
        }
    ]
    summary = SymbolEvalSummary(
        symbol="HD",
        verdict="HOLD",
        final_verdict="HOLD",
        score=50,
        band="D",
        primary_reason="No contract passed (rejected_due_to_delta=5)",
        stage_status="STAGE2_CHAIN",
        stage1_status="PASS",
        stage2_status="FAIL",
        provider_status="OK",
        data_freshness=None,
        evaluated_at=None,
        strategy="CSP",
        price=400.0,
        expiration=None,
        has_candidates=False,
        candidate_count=0,
    )
    diagnostics_details = SymbolDiagnosticsDetails(
        technicals={},
        exit_plan={"t1": None, "t2": None, "t3": None, "stop": None},
        risk_flags={},
        explanation={},
        stock={},
        symbol_eligibility={"status": "FAIL", "reasons": ["rejected_due_to_delta"]},
        liquidity={},
        sample_rejected_due_to_delta=sample,
    )
    mock_store = MagicMock()
    mock_store.get_symbol.return_value = (summary, [], [], None, diagnostics_details)
    mock_store.get_latest.return_value = None

    from app.api.server import app

    with patch("app.core.eval.evaluation_store_v2.get_evaluation_store_v2", return_value=mock_store):
        client = TestClient(app)
        r = client.get("/api/ui/symbol-diagnostics?symbol=HD")
    assert r.status_code == 200
    data = r.json()
    reasons = data.get("reasons_explained") or []
    assert len(reasons) >= 1
    delta_reason = next((x for x in reasons if x.get("code") == "rejected_due_to_delta"), None)
    assert delta_reason is not None
    msg = delta_reason.get("message") or ""
    assert "abs(delta)" in msg
    assert "0.55" in msg
    assert "55" in msg
    assert "0.20" in msg
    assert "0.40" in msg
    assert "outside target range" in msg
    assert "See diagnostics for details" not in msg or "0.55" in msg
    sample_in_response = data.get("sample_rejected_due_to_delta") or []
    assert len(sample_in_response) >= 1
    assert sample_in_response[0].get("observed_delta_decimal_abs") == 0.55
