# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Symbol-diagnostics must be live-only: never call load_latest_run for verdict/gates/blockers.
Proves response has live_evaluation=true and no from_persisted_run / run_id in eligibility.
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@pytest.mark.skipif(not _HAS_FASTAPI, reason="requires FastAPI (optional dependency)")
def test_symbol_diagnostics_never_calls_load_latest_run():
    """
    Patch load_latest_run to raise if called; call symbol-diagnostics; assert 200 and live-only response.
    Proves the handler does not use evaluation_store.load_latest_run.
    """
    from unittest.mock import patch, MagicMock
    from app.api.server import app
    from app.core.data.symbol_snapshot_service import SymbolSnapshot
    from app.core.eval.staged_evaluator import (
        FullEvaluationResult,
        Stage2Result,
        EvaluationStage,
        FinalVerdict,
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("load_latest_run must not be called in symbol-diagnostics")

    client = TestClient(app)

    # Minimal Stage2Result for live path
    stage2 = Stage2Result(
        symbol="SPY",
        expirations_available=2,
        expirations_evaluated=2,
        contracts_evaluated=50,
        liquidity_ok=True,
        liquidity_reason="OK",
    )
    mock_full = FullEvaluationResult(
        symbol="SPY",
        source="ORATS",
        stage_reached=EvaluationStage.STAGE2_CHAIN,
        final_verdict=FinalVerdict.ELIGIBLE,
        verdict="ELIGIBLE",
        primary_reason="Chain evaluated",
        confidence=0.8,
        score=75,
        gates=[{"name": "Stock Quality (Stage 1)", "status": "PASS", "reason": "OK"}],
        blockers=[],
        candidate_trades=[],
        stage2=stage2,
    )

    with patch("app.core.eval.evaluation_store.load_latest_run", side_effect=fail_if_called):
        with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_snap:
            mock_snap.return_value = SymbolSnapshot(
                ticker="SPY",
                price=500.0,
                bid=499.9,
                ask=500.1,
                volume=10_000_000,
                quote_date="2026-02-10",
                iv_rank=40.0,
                quote_as_of="2026-02-10T16:00:00Z",
                field_sources={"price": "delayed_strikes_ivrank"},
                missing_reasons={},
            )
            with patch("app.core.eval.staged_evaluator.evaluate_symbol_full", return_value=mock_full):
                r = client.get("/api/view/symbol-diagnostics", params={"symbol": "SPY"})

    assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text[:500]}"
    data = r.json()

    assert data.get("live_evaluation") is True, "response must include live_evaluation: true"
    eligibility = data.get("eligibility") or {}
    assert "from_persisted_run" not in eligibility, "eligibility must not contain from_persisted_run"
    assert "run_id" not in eligibility, "eligibility must not contain run_id"
