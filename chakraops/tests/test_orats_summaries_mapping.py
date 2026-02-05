# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Unit tests for ORATS /live/summaries to StockSnapshot field mapping.

Validates that:
1. Available fields (stockPrice, iv30d, iv1y) are correctly extracted
2. Unavailable fields (bid, ask, volume, avgVolume) are set to None
3. IV rank is computed from iv30d/iv1y ratio
4. data_quality_details reflects actual field availability
"""

from unittest.mock import patch

import pytest


# Frozen ORATS /live/summaries response fixture (based on actual API observation)
MOCK_ORATS_SUMMARIES_RESPONSE = [
    {
        "ticker": "AAPL",
        "tradeDate": "2026-02-05",
        "stockPrice": 275.45,
        "iv30d": 0.2850,
        "iv1y": 0.2825,
        "iv10d": 0.2920,
        "iv20d": 0.2880,
        "iv2m": 0.2810,
        "iv3m": 0.2790,
        "iv6m": 0.2750,
        "iv90d": 0.2800,
        "impliedMove": 0.0412,
        "slope": -0.0015,
        "mktCap": 4250000000000,
        "mktWidth": 0.0008,
        "contango": 0.015,
        "orIv30d": 0.2852,
        "updatedAt": "2026-02-05T16:30:00Z",
        # NOTE: bid, ask, volume, avgVolume are NOT present in ORATS response
    }
]


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_extracts_price_from_summaries(mock_get_summaries):
    """Stage 1 extracts stockPrice as the equity price."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    assert result.price == 275.45, "stockPrice should be extracted as price"
    mock_get_summaries.assert_called_once_with("AAPL")


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_computes_iv_rank_from_ratio(mock_get_summaries):
    """Stage 1 computes IV rank from iv30d/iv1y ratio."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    # iv30d=0.2850, iv1y=0.2825 -> ratio=1.0088 -> rank=1.0088*50=50.44
    expected_ratio = 0.2850 / 0.2825
    expected_iv_rank = expected_ratio * 50
    
    assert result.iv_rank is not None, "iv_rank should be computed"
    assert abs(result.iv_rank - expected_iv_rank) < 0.1, f"iv_rank should be ~{expected_iv_rank:.1f}"


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_sets_unavailable_fields_to_none(mock_get_summaries):
    """Stage 1 sets bid, ask, volume, avg_volume to None (not in ORATS summaries)."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    # These fields are NOT in ORATS /live/summaries
    assert result.bid is None, "bid should be None (not in ORATS summaries)"
    assert result.ask is None, "ask should be None (not in ORATS summaries)"
    assert result.volume is None, "volume should be None (not in ORATS summaries)"
    assert result.avg_volume is None, "avg_volume should be None (not in ORATS summaries)"


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_data_quality_reflects_field_availability(mock_get_summaries):
    """data_quality_details shows which fields are VALID vs MISSING."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    # Available fields should be VALID
    assert result.data_quality_details.get("price") == "VALID"
    assert result.data_quality_details.get("iv_rank") == "VALID"
    
    # Unavailable fields should be MISSING
    assert result.data_quality_details.get("bid") == "MISSING"
    assert result.data_quality_details.get("ask") == "MISSING"
    assert result.data_quality_details.get("volume") == "MISSING"
    assert result.data_quality_details.get("avg_volume") == "MISSING"


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_missing_fields_list_is_accurate(mock_get_summaries):
    """missing_fields list contains only the fields not in ORATS summaries."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("AAPL")
    
    # bid, ask, volume, avg_volume are missing (not in ORATS summaries)
    expected_missing = {"bid", "ask", "volume", "avg_volume"}
    actual_missing = set(result.missing_fields)
    
    assert expected_missing == actual_missing, (
        f"missing_fields should be {expected_missing}, got {actual_missing}"
    )


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_qualifies_with_price_and_iv_rank(mock_get_summaries):
    """Stage 1 should QUALIFY a symbol with price and iv_rank, despite missing equity fields."""
    mock_get_summaries.return_value = MOCK_ORATS_SUMMARIES_RESPONSE
    
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
    
    result = evaluate_stage1("AAPL")
    
    # Should be QUALIFIED because price and iv_rank are available
    # Missing bid/ask/volume/avg_volume are INTRADAY_ONLY and don't block
    assert result.stock_verdict == StockVerdict.QUALIFIED, (
        f"Stock should be QUALIFIED, got {result.stock_verdict} ({result.stock_verdict_reason})"
    )


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_handles_missing_price_as_fatal(mock_get_summaries):
    """Stage 1 should treat missing stockPrice as fatal."""
    # Response with no stockPrice
    mock_get_summaries.return_value = [
        {
            "ticker": "BAD",
            "iv30d": 0.25,
            "iv1y": 0.24,
        }
    ]
    
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict
    
    result = evaluate_stage1("BAD")
    
    # Missing price is FATAL - should not be QUALIFIED
    assert result.stock_verdict in (StockVerdict.HOLD, StockVerdict.ERROR, StockVerdict.BLOCKED), (
        f"Missing price should result in HOLD/ERROR/BLOCKED, got {result.stock_verdict}"
    )
    assert result.price is None
    assert "price" in result.missing_fields


@patch("app.core.orats.orats_client.get_orats_live_summaries")
def test_stage1_iv_rank_clamped_to_0_100(mock_get_summaries):
    """IV rank computation should be clamped to 0-100 range."""
    # Extreme case: iv30d much higher than iv1y
    mock_get_summaries.return_value = [
        {
            "ticker": "HIGH",
            "stockPrice": 100.0,
            "iv30d": 1.0,  # 100% IV
            "iv1y": 0.2,   # 20% IV
        }
    ]
    
    from app.core.eval.staged_evaluator import evaluate_stage1
    
    result = evaluate_stage1("HIGH")
    
    # iv_ratio = 1.0/0.2 = 5.0, rank = 5.0 * 50 = 250 -> clamped to 100
    assert result.iv_rank is not None
    assert result.iv_rank == 100.0, f"iv_rank should be clamped to 100, got {result.iv_rank}"
