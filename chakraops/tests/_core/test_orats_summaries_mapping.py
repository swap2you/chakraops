# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Unit tests for ORATS equity snapshot to Stage1Result field mapping.

Validates that:
1. Available fields (price, iv_rank) are correctly extracted from canonical snapshot
2. Unavailable fields (bid, ask, volume) are set to None; volume metrics are avg_option_volume_20d / avg_stock_volume_20d only
3. IV rank is passed through from snapshot
4. data_quality_details reflects actual field availability

Stage 1 uses get_snapshot (symbol_snapshot_service). All tests patch get_snapshot to avoid live ORATS.
"""

from datetime import date
from unittest.mock import patch

import pytest

from app.core.data.symbol_snapshot_service import SymbolSnapshot


def _make_canonical_snapshot(
    symbol: str = "AAPL",
    price: float | None = 275.45,
    iv_rank: float | None = (0.2850 / 0.2825) * 50,
    bid: float | None = None,
    ask: float | None = None,
    volume: int | None = None,
    quote_date: str | None = "2026-02-05",
    avg_option_volume_20d: float | None = None,
    avg_stock_volume_20d: float | None = None,
) -> SymbolSnapshot:
    """Build SymbolSnapshot for tests. No avg_volume (forbidden)."""
    return SymbolSnapshot(
        ticker=symbol.upper(),
        price=price,
        bid=bid,
        ask=ask,
        volume=volume,
        quote_date=quote_date,
        iv_rank=iv_rank,
        stock_volume_today=None,
        avg_option_volume_20d=avg_option_volume_20d,
        avg_stock_volume_20d=avg_stock_volume_20d,
        quote_as_of=quote_date or "",
        core_as_of=None,
        derived_as_of=None,
        field_sources={},
        missing_reasons={},
    )


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_extracts_price_from_summaries(mock_get_snapshot):
    """Stage 1 extracts price from canonical snapshot."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(price=275.45)

    from app.core.eval.staged_evaluator import evaluate_stage1

    result = evaluate_stage1("AAPL")

    assert result.price == 275.45, "price should be extracted from snapshot"
    mock_get_snapshot.assert_called_once()
    call_args = mock_get_snapshot.call_args[0][0]
    assert call_args == "AAPL"


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_computes_iv_rank_from_ratio(mock_get_snapshot):
    """Stage 1 passes through iv_rank from snapshot."""
    expected_iv_rank = (0.2850 / 0.2825) * 50
    mock_get_snapshot.return_value = _make_canonical_snapshot(price=275.45, iv_rank=expected_iv_rank)

    from app.core.eval.staged_evaluator import evaluate_stage1

    result = evaluate_stage1("AAPL")

    assert result.iv_rank is not None, "iv_rank should be set"
    assert abs(result.iv_rank - expected_iv_rank) < 0.1, f"iv_rank should be ~{expected_iv_rank:.1f}"


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_sets_unavailable_fields_to_none(mock_get_snapshot):
    """Stage 1 sets bid, ask, volume to None when not in snapshot; volume metrics are avg_option_volume_20d/avg_stock_volume_20d."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(price=275.45, bid=None, ask=None, volume=None)

    from app.core.eval.staged_evaluator import evaluate_stage1

    result = evaluate_stage1("AAPL")

    assert result.bid is None, "bid should be None"
    assert result.ask is None, "ask should be None"
    assert result.volume is None, "volume should be None"
    assert getattr(result, "avg_option_volume_20d", None) is None
    assert getattr(result, "avg_stock_volume_20d", None) is None


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_data_quality_reflects_field_availability(mock_get_snapshot):
    """data_quality_details shows which fields are VALID vs MISSING. No avg_volume (forbidden)."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(price=275.45)

    from app.core.eval.staged_evaluator import evaluate_stage1

    result = evaluate_stage1("AAPL")

    assert result.data_quality_details.get("price") == "VALID"
    assert result.data_quality_details.get("iv_rank") == "VALID"
    assert result.data_quality_details.get("bid") == "MISSING"
    assert result.data_quality_details.get("ask") == "MISSING"
    assert result.data_quality_details.get("volume") == "MISSING"
    assert "avg_volume" not in result.data_quality_details


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_missing_fields_list_is_accurate(mock_get_snapshot):
    """missing_fields list contains required fields that are missing. EQUITY requires bid/ask/volume."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(price=275.45)

    from app.core.symbols.instrument_type import InstrumentType
    from app.core.eval.staged_evaluator import evaluate_stage1

    with patch("app.core.symbols.instrument_type.classify_instrument", return_value=InstrumentType.EQUITY):
        result = evaluate_stage1("AAPL")
    expected_missing = {"bid", "ask", "volume"}
    actual_missing = set(result.missing_fields)
    assert expected_missing == actual_missing, (
        f"missing_fields should be {expected_missing}, got {actual_missing}"
    )


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_qualifies_with_price_and_iv_rank(mock_get_snapshot):
    """Stage 1 should QUALIFY when required fields present (price, bid, ask, volume, quote_date, iv_rank)."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(
        price=275.45, bid=275.4, ask=275.5, volume=1_000_000, iv_rank=50.0, quote_date=date.today().isoformat()
    )

    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict

    result = evaluate_stage1("AAPL")

    assert result.stock_verdict == StockVerdict.QUALIFIED, (
        f"Stock should be QUALIFIED, got {result.stock_verdict} ({result.stock_verdict_reason})"
    )


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_handles_missing_price_as_fatal(mock_get_snapshot):
    """Stage 1 should treat missing price as BLOCKED."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(symbol="BAD", price=None, iv_rank=50.0)

    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict

    result = evaluate_stage1("BAD")

    assert result.stock_verdict == StockVerdict.BLOCKED, (
        f"Missing price should result in BLOCKED, got {result.stock_verdict}"
    )
    assert result.price is None
    assert "price" in result.missing_fields


@patch("app.core.data.symbol_snapshot_service.get_snapshot")
def test_stage1_iv_rank_clamped_to_0_100(mock_get_snapshot):
    """IV rank from snapshot is used as-is."""
    mock_get_snapshot.return_value = _make_canonical_snapshot(symbol="HIGH", price=100.0, bid=99.9, ask=100.1, volume=1_000_000, iv_rank=100.0, quote_date="2026-02-05")

    from app.core.eval.staged_evaluator import evaluate_stage1

    result = evaluate_stage1("HIGH")

    assert result.iv_rank is not None
    assert result.iv_rank == 100.0, f"iv_rank should be 100, got {result.iv_rank}"
