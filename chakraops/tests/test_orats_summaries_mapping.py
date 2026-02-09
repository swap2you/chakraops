# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Unit tests for ORATS equity snapshot to Stage1Result field mapping.

Validates that:
1. Available fields (price, iv_rank) are correctly extracted from FullEquitySnapshot
2. Unavailable fields (bid, ask, volume, avg_volume) are set to None
3. IV rank is passed through from snapshot
4. data_quality_details reflects actual field availability

Stage 1 uses fetch_full_equity_snapshots (orats_equity_quote), not get_orats_live_summaries.
All tests patch fetch_full_equity_snapshots to avoid live ORATS.
"""

from unittest.mock import patch

import pytest

from app.core.orats.orats_equity_quote import FullEquitySnapshot


def _make_snapshot(
    symbol: str = "AAPL",
    price: float | None = 275.45,
    iv_rank: float | None = (0.2850 / 0.2825) * 50,
    bid: float | None = None,
    ask: float | None = None,
    volume: int | None = None,
    avg_volume: int | None = None,
    quote_date: str | None = "2026-02-05",
) -> FullEquitySnapshot:
    """Build FullEquitySnapshot for tests. Missing fields inferred from None values."""
    missing = []
    if price is None:
        missing.append("price")
    if bid is None:
        missing.append("bid")
    if ask is None:
        missing.append("ask")
    if volume is None:
        missing.append("volume")
    missing.append("avg_volume")  # Never available from ORATS
    if iv_rank is None:
        missing.append("iv_rank")
    raw = []
    if price is not None:
        raw.append("price")
    if bid is not None:
        raw.append("bid")
    if ask is not None:
        raw.append("ask")
    if volume is not None:
        raw.append("volume")
    if iv_rank is not None:
        raw.append("iv_rank")
    sources = {}
    if price is not None:
        sources["price"] = "strikes/options"
    if bid is not None:
        sources["bid"] = "strikes/options"
    if ask is not None:
        sources["ask"] = "strikes/options"
    if volume is not None:
        sources["volume"] = "strikes/options"
    if iv_rank is not None:
        sources["iv_rank"] = "ivrank"
    return FullEquitySnapshot(
        symbol=symbol.upper(),
        price=price,
        bid=bid,
        ask=ask,
        volume=volume,
        avg_volume=avg_volume,
        iv_rank=iv_rank,
        quote_date=quote_date,
        data_sources=sources,
        raw_fields_present=raw,
        missing_fields=missing,
        missing_reasons={f: "Not in ORATS response" for f in missing},
    )


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_extracts_price_from_summaries(mock_fetch):
    """Stage 1 extracts price from equity snapshot."""
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    assert result.price == 275.45, "price should be extracted from snapshot"
    mock_fetch.assert_called_once()
    call_args = mock_fetch.call_args[0][0]
    assert call_args == ["AAPL"]


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_computes_iv_rank_from_ratio(mock_fetch):
    """Stage 1 passes through iv_rank from snapshot."""
    expected_iv_rank = (0.2850 / 0.2825) * 50
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45, iv_rank=expected_iv_rank)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    assert result.iv_rank is not None, "iv_rank should be set"
    assert abs(result.iv_rank - expected_iv_rank) < 0.1, f"iv_rank should be ~{expected_iv_rank:.1f}"


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_sets_unavailable_fields_to_none(mock_fetch):
    """Stage 1 sets bid, ask, volume, avg_volume to None when not in snapshot."""
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45, bid=None, ask=None, volume=None, avg_volume=None)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    assert result.bid is None, "bid should be None"
    assert result.ask is None, "ask should be None"
    assert result.volume is None, "volume should be None"
    assert result.avg_volume is None, "avg_volume should be None"


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_data_quality_reflects_field_availability(mock_fetch):
    """data_quality_details shows which fields are VALID vs MISSING."""
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    assert result.data_quality_details.get("price") == "VALID"
    assert result.data_quality_details.get("iv_rank") == "VALID"
    assert result.data_quality_details.get("bid") == "MISSING"
    assert result.data_quality_details.get("ask") == "MISSING"
    assert result.data_quality_details.get("volume") == "MISSING"
    assert result.data_quality_details.get("avg_volume") == "MISSING"


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_missing_fields_list_is_accurate(mock_fetch):
    """missing_fields list contains only the fields not in snapshot."""
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    expected_missing = {"bid", "ask", "volume", "avg_volume"}
    actual_missing = set(result.missing_fields)
    assert expected_missing == actual_missing, (
        f"missing_fields should be {expected_missing}, got {actual_missing}"
    )


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_qualifies_with_price_and_iv_rank(mock_fetch):
    """Stage 1 should QUALIFY a symbol with price and iv_rank, despite missing equity fields."""
    mock_fetch.return_value = {"AAPL": _make_snapshot(price=275.45)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
    
    result = evaluate_stage1("AAPL")
    
    assert result.stock_verdict == StockVerdict.QUALIFIED, (
        f"Stock should be QUALIFIED, got {result.stock_verdict} ({result.stock_verdict_reason})"
    )


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_handles_missing_price_as_fatal(mock_fetch):
    """Stage 1 should treat missing price as fatal."""
    mock_fetch.return_value = {"BAD": _make_snapshot(symbol="BAD", price=None, iv_rank=50.0)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
    
    result = evaluate_stage1("BAD")
    
    assert result.stock_verdict in (StockVerdict.HOLD, StockVerdict.ERROR, StockVerdict.BLOCKED), (
        f"Missing price should result in HOLD/ERROR/BLOCKED, got {result.stock_verdict}"
    )
    assert result.price is None
    assert "price" in result.missing_fields


@patch("app.core.orats.orats_equity_quote.fetch_full_equity_snapshots")
def test_stage1_iv_rank_clamped_to_0_100(mock_fetch):
    """IV rank from snapshot can be high; evaluator uses as-is (clamping is in snapshot source)."""
    mock_fetch.return_value = {"HIGH": _make_snapshot(symbol="HIGH", price=100.0, iv_rank=100.0)}
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("HIGH")
    
    assert result.iv_rank is not None
    assert result.iv_rank == 100.0, f"iv_rank should be 100, got {result.iv_rank}"
