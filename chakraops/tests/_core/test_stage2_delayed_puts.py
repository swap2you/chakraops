# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3.6/3.7: Stage-2 V2-only; evaluate_stage2 uses run_csp_stage2_v2 / run_cc_stage2_v2."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.eval.staged_evaluator import evaluate_stage2, Stage1Result, StockVerdict


def _make_qualified_stage1(symbol: str = "SPY", price: float = 505.0) -> Stage1Result:
    """Stage1 that qualifies for stage 2 with price for spot_used."""
    r = Stage1Result(
        symbol=symbol,
        stock_verdict=StockVerdict.QUALIFIED,
        stock_verdict_reason="qualified",
        stage1_score=70,
    )
    r.price = price
    return r


def _make_v2_result(puts_requested: int = 10, selected: bool = True):
    """Stage2V2Result-like object for mocking."""
    trace = {
        "mode": "CSP",
        "spot_used": 505.0,
        "expirations_in_window": ["2026-03-20"],
        "expirations_count": 1,
        "request_counts": {"puts_requested": puts_requested, "calls_requested": 0},
        "response_rows": puts_requested,
        "puts_with_required_fields": puts_requested,
        "calls_with_required_fields": 0,
        "otm_contracts_in_dte": puts_requested,
        "otm_contracts_in_delta_band": 5,
        "otm_puts_in_dte": puts_requested,
        "otm_puts_in_delta_band": 5,
        "delta_abs_stats": {"min": 0.20, "median": 0.30, "max": 0.40},
        "rejection_counts": {},
        "top_candidates_table": [],
        "sample_request_symbols": ["SPY260320P00500000"],
    }
    st = {
        "symbol": "SPY",
        "exp": "2026-03-20",
        "strike": 500.0,
        "abs_delta": 0.25,
        "bid": 2.50,
        "ask": 2.70,
        "credit_estimate": 2.50,
        "spread_pct": 0.02,
        "oi": 600,
    } if selected else None
    return SimpleNamespace(
        success=selected,
        error_code=None,
        spot_used=505.0,
        available=True,
        selected_trade=st,
        top_rejection=None if selected else "rejected_due_to_delta=5",
        top_rejection_reason=None if selected else "rejected_due_to_delta=5",
        sample_rejections=[],
        top_candidates=[],
        stage2_trace=trace,
        contract_count=puts_requested,
    )


@patch("app.core.options.v2.run_csp_stage2_v2")
def test_stage2_v2_produces_puts_seen(mock_run_v2):
    """
    V2 path returns option_type_counts with puts_seen from request_counts.
    """
    mock_run_v2.return_value = _make_v2_result(puts_requested=15, selected=True)

    stage1 = _make_qualified_stage1(price=505.0)
    result = evaluate_stage2("SPY", stage1, chain_provider=None, strategy_mode="CSP")

    assert result.option_type_counts["puts_seen"] == 15
    assert result.option_type_counts["calls_seen"] == 0
    assert result.contracts_evaluated == 15
    assert result.liquidity_ok is True


@patch("app.core.options.v2.run_csp_stage2_v2")
def test_stage2_v2_uses_csp_engine(mock_run_v2):
    """
    When strategy_mode=CSP, evaluate_stage2 calls run_csp_stage2_v2.
    """
    mock_run_v2.return_value = _make_v2_result(puts_requested=10, selected=True)

    stage1 = _make_qualified_stage1(price=505.0)
    evaluate_stage2("SPY", stage1, chain_provider=None, strategy_mode="CSP")

    mock_run_v2.assert_called_once()
    call_kw = mock_run_v2.call_args[1]
    assert call_kw["symbol"] == "SPY"
    assert call_kw["spot_used"] == 505.0


@patch("app.core.options.v2.run_cc_stage2_v2")
def test_stage2_v2_uses_cc_engine_for_cc_mode(mock_run_cc):
    """
    When strategy_mode=CC, evaluate_stage2 calls run_cc_stage2_v2.
    """
    v2_result = SimpleNamespace(
        success=True,
        error_code=None,
        spot_used=505.0,
        available=True,
        selected_trade={"symbol": "SPY", "exp": "2026-03-20", "strike": 510.0, "abs_delta": 0.30, "bid": 3.0, "ask": 3.1, "oi": 500},
        top_rejection=None,
        top_rejection_reason=None,
        sample_rejections=[],
        top_candidates=[],
        stage2_trace={
            "mode": "CC",
            "request_counts": {"puts_requested": 0, "calls_requested": 20},
            "response_rows": 20,
            "otm_calls_in_delta_band": 5,
            "expirations_count": 1,
        },
        contract_count=20,
    )
    mock_run_cc.return_value = v2_result

    stage1 = _make_qualified_stage1(price=505.0)
    result = evaluate_stage2("SPY", stage1, chain_provider=None, strategy_mode="CC")

    mock_run_cc.assert_called_once()
    assert result.option_type_counts["calls_seen"] == 20
    assert result.option_type_counts["puts_seen"] == 0


def test_fetch_base_chain_omits_delta_param():
    """
    fetch_base_chain does NOT pass delta to ORATS /strikes.
    Delta filtering is applied post-fetch; ORATS /strikes returns all strikes.
    """
    from app.core.options.orats_chain_pipeline import fetch_base_chain

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
        mock_get.return_value = mock_response
        fetch_base_chain("SPY", dte_min=30, dte_max=45, chain_mode="DELAYED")
        params = mock_get.call_args[1].get("params", {})
        assert "delta" not in params
        assert "dte" in params
        assert "ticker" in params

    with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
        mock_get.return_value = mock_response
        fetch_base_chain(
            "SPY", dte_min=30, dte_max=45, chain_mode="DELAYED",
            delta_lo=0.10, delta_hi=0.45,
        )
        params = mock_get.call_args[1].get("params", {})
        # Delta is used for local filtering, not sent to ORATS
        assert "delta" not in params
        assert "dte" in params
        assert "ticker" in params
