# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3 HOTFIX: Stage-2 uses DELAYED chain; option_type_counts puts_seen > 0."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.eval.staged_evaluator import evaluate_stage2, Stage1Result, StockVerdict
from app.core.options.orats_chain_provider import OratsChainProvider
from app.core.options.orats_chain_pipeline import EnrichedContract, OptionChainResult
from app.market.market_hours import get_stage2_chain_source


def _make_qualified_stage1(symbol: str = "SPY") -> Stage1Result:
    """Stage1 that qualifies for stage 2."""
    return Stage1Result(
        symbol=symbol,
        stock_verdict=StockVerdict.QUALIFIED,
        stock_verdict_reason="qualified",
        stage1_score=70,
    )


def _make_enriched_put(exp: date, strike: float = 500.0, delta: float = -0.25) -> EnrichedContract:
    """EnrichedContract with option_type=PUT for DELAYED pipeline mock."""
    return EnrichedContract(
        symbol="SPY",
        expiration=exp,
        strike=strike,
        option_type="PUT",
        opra_symbol="SPY  250321P00500000",
        dte=35,
        bid=2.50,
        ask=2.70,
        mid=2.60,
        open_interest=600,
        delta=delta,
        enriched=True,
    )


@patch("app.core.options.orats_chain_pipeline.fetch_option_chain")
@patch("app.core.options.orats_chain_pipeline.fetch_base_chain")
def test_stage2_delayed_chain_produces_puts_seen(
    mock_fetch_base,
    mock_fetch_option,
):
    """
    DELAYED chain pipeline returns per-contract option_type; option_type_counts puts_seen > 0.
    """
    exp = date.today() + timedelta(days=35)
    put_contract = _make_enriched_put(exp)

    # get_expirations (fetch_base_chain) returns base contracts with expiration
    base_contract = SimpleNamespace(expiration=exp, option_type="PUT", strike=500.0)
    mock_fetch_base.return_value = ([base_contract], 505.0, None, 100)

    # fetch_option_chain returns OptionChainResult with puts
    chain_result = OptionChainResult(
        symbol="SPY",
        underlying_price=505.0,
        contracts=[put_contract],
        error=None,
    )
    mock_fetch_option.return_value = chain_result

    provider = OratsChainProvider(use_cache=False, chain_source="DELAYED")
    stage1 = _make_qualified_stage1()
    result = evaluate_stage2("SPY", stage1, chain_provider=provider)

    assert result.option_type_counts["puts_seen"] > 0
    assert result.option_type_counts["puts_seen"] >= 1
    assert result.contracts_evaluated >= 1


@patch("app.market.market_hours.get_market_phase", return_value="OPEN")
def test_stage2_uses_delayed_when_no_provider_passed(mock_phase):
    """
    When chain_provider=None, evaluate_stage2 uses get_chain_provider(chain_source=get_stage2_chain_source()).
    Provider must be DELAYED even when market is OPEN.
    """
    with patch("app.core.options.orats_chain_pipeline.fetch_option_chain") as m_opt:
        with patch("app.core.options.orats_chain_pipeline.fetch_base_chain") as m_base:
            exp = date.today() + timedelta(days=35)
            put_contract = _make_enriched_put(exp)
            base_contract = SimpleNamespace(expiration=exp, option_type="PUT", strike=500.0)
            m_base.return_value = ([base_contract], 505.0, None, 100)
            m_opt.return_value = OptionChainResult(
                symbol="SPY",
                underlying_price=505.0,
                contracts=[put_contract],
                error=None,
            )
            stage1 = _make_qualified_stage1()
            # Pass chain_provider=None so evaluate_stage2 resolves via get_stage2_chain_source
            result = evaluate_stage2("SPY", stage1, chain_provider=None)
    # If DELAYED was used, fetch_option_chain would be called (DELAYED path uses pipeline)
    # If LIVE was used, get_orats_live_strikes would be called instead
    m_opt.assert_called()
    assert result.option_type_counts.get("puts_seen", 0) >= 1


def test_fetch_base_chain_passes_delta_when_provided():
    """
    fetch_base_chain passes delta param to ORATS when delta_lo/delta_hi are provided (Stage-2).
    When not provided, delta is omitted (chain discovery only).
    """
    from app.core.options.orats_chain_pipeline import fetch_base_chain

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": []}

    with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
        mock_get.return_value = mock_response
        fetch_base_chain("SPY", dte_min=30, dte_max=45, chain_mode="DELAYED")
        call_kw = mock_get.call_args[1]
        params = call_kw.get("params", {})
        assert "delta" not in params
        assert "dte" in params
        assert "ticker" in params

    with patch("app.core.options.orats_chain_pipeline.requests.get") as mock_get:
        mock_get.return_value = mock_response
        fetch_base_chain(
            "SPY", dte_min=30, dte_max=45, chain_mode="DELAYED",
            delta_lo=0.10, delta_hi=0.45,
        )
        call_kw = mock_get.call_args[1]
        params = call_kw.get("params", {})
        assert params.get("delta") in ("0.1,0.45", "0.10,0.45")  # float formatting may drop trailing zero
        assert "dte" in params
        assert "ticker" in params
