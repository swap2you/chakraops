# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
DATA_REQUIREMENTS contract tests. Must pass for ORATS integration to be correct.

- Fail if a non-existent field (e.g. avg_volume) is referenced in contract code.
- Fail if live endpoints are used for equity quotes.
- Fail if Stage-1 allows evaluation to proceed with missing required data.
"""

from __future__ import annotations

import pytest

from app.core.data.data_requirements import (
    FORBIDDEN_FIELD_NAMES,
    REQUIRED_STAGE1_FIELDS,
    VOLUME_METRICS_ALLOWED,
    EQUITY_QUOTE_SOURCE,
    LIVE_PATHS_FORBIDDEN_FOR_EQUITY,
)


def test_forbidden_field_avg_volume():
    """avg_volume must be in FORBIDDEN_FIELD_NAMES and must not be used."""
    assert "avg_volume" in FORBIDDEN_FIELD_NAMES


def test_volume_metrics_only_allowed():
    """Volume metrics are only avg_option_volume_20d and avg_stock_volume_20d."""
    assert "avg_option_volume_20d" in VOLUME_METRICS_ALLOWED
    assert "avg_stock_volume_20d" in VOLUME_METRICS_ALLOWED
    assert "avg_volume" not in VOLUME_METRICS_ALLOWED


def test_equity_quote_source_is_delayed():
    """Equity quote must come from delayed, not live."""
    assert "live" not in EQUITY_QUOTE_SOURCE.lower()
    assert "delayed" in EQUITY_QUOTE_SOURCE.lower()


def test_live_paths_forbidden():
    """Live paths must be explicitly forbidden for equity."""
    assert any("live" in p for p in LIVE_PATHS_FORBIDDEN_FOR_EQUITY)


def test_required_stage1_fields():
    """Stage-1 required fields must include price, bid, ask, volume, quote_date, iv_rank."""
    required = set(REQUIRED_STAGE1_FIELDS)
    assert "price" in required
    assert "bid" in required
    assert "ask" in required
    assert "volume" in required
    assert "quote_date" in required
    assert "iv_rank" in required
    assert "avg_volume" not in required


def test_stage1_blocks_on_missing_required():
    """Stage-1 must BLOCK when required field is missing (no PASS)."""
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict

    # Mock canonical snapshot with missing price
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="TEST",
            price=None,
            bid=1.0,
            ask=1.0,
            volume=1000,
            quote_date="2026-02-09",
            iv_rank=50.0,
            field_sources={},
            missing_reasons={"price": "missing"},
        )
        result = evaluate_stage1("TEST")
    assert result.stock_verdict == StockVerdict.BLOCKED
    assert "missing" in result.stock_verdict_reason.lower() or "incomplete" in result.stock_verdict_reason.lower()


def test_stage1_blocks_on_missing_bid_ask_volume():
    """Stage-1 must BLOCK when bid, ask, or volume is missing (strict; no OPRA waiver)."""
    from unittest.mock import patch
    from app.core.data.symbol_snapshot_service import SymbolSnapshot
    from app.core.eval.staged_evaluator import evaluate_stage1, StockVerdict

    # Snapshot with price/quote_date/iv_rank but missing bid/ask/volume
    with patch("app.core.data.symbol_snapshot_service.get_snapshot") as mock_get:
        mock_get.return_value = SymbolSnapshot(
            ticker="TEST",
            price=100.0,
            bid=None,
            ask=None,
            volume=None,
            quote_date="2026-02-09",
            iv_rank=50.0,
            field_sources={},
            missing_reasons={"bid": "missing", "ask": "missing", "volume": "missing"},
        )
        result = evaluate_stage1("TEST")
    assert result.stock_verdict == StockVerdict.BLOCKED
    assert "bid" in result.missing_fields or "ask" in result.missing_fields or "volume" in result.missing_fields
    assert "incomplete" in result.stock_verdict_reason.lower() or "missing" in result.stock_verdict_reason.lower()


def test_compute_required_missing_iv_rank_present():
    """When symbol dict has iv_rank set, required_data_missing must NOT include iv_rank."""
    from app.core.symbols.data_dependencies import compute_required_missing
    sym = {"symbol": "SPY", "price": 450.0, "bid": 449.0, "ask": 451.0, "volume": 1_000_000, "quote_date": "2026-02-17", "iv_rank": 25.0}
    missing = compute_required_missing(sym)
    assert "iv_rank" not in missing


def test_compute_required_missing_iv_rank_absent():
    """When symbol dict has iv_rank None/missing, required_data_missing must include iv_rank."""
    from app.core.symbols.data_dependencies import compute_required_missing
    sym = {"symbol": "SPY", "price": 450.0, "bid": 449.0, "ask": 451.0, "volume": 1_000_000, "quote_date": "2026-02-17", "iv_rank": None}
    missing = compute_required_missing(sym)
    assert "iv_rank" in missing


def test_no_avg_volume_in_optional_evaluation_fields():
    """data_dependencies must not list avg_volume as optional."""
    from app.core.symbols.data_dependencies import OPTIONAL_EVALUATION_FIELDS
    assert "avg_volume" not in OPTIONAL_EVALUATION_FIELDS


def test_snapshot_avg_stock_volume_20d_missing_reasons_when_hist_dailies_no_rows():
    """When hist/dailies returns no rows, avg_stock_volume_20d must have missing_reasons explaining why. Stage1 BLOCKs if required."""
    from unittest.mock import patch, MagicMock
    from app.core.data.symbol_snapshot_service import get_snapshot

    # FullEquitySnapshot-like object for delayed quote
    delayed = MagicMock()
    delayed.price = 100.0
    delayed.bid = 99.9
    delayed.ask = 100.1
    delayed.volume = 1_000_000
    delayed.quote_date = "2026-02-09"
    delayed.iv_rank = 50.0

    with patch("app.core.data.orats_client.fetch_full_equity_snapshots") as mock_fetch_full:
        mock_fetch_full.return_value = {"TKR": delayed}
        with patch("app.core.orats.orats_core_client.fetch_core_snapshot") as mock_core:
            mock_core.return_value = {"ticker": "TKR", "stkVolu": 2_000_000, "avgOptVolu20d": 50_000.0}
            with patch("app.core.config.orats_secrets.ORATS_API_TOKEN", "test-token"):
                with patch("app.core.orats.orats_core_client.derive_avg_stock_volume_20d", return_value=None):
                    snapshot = get_snapshot("TKR", derive_avg_stock_volume_20d=True, use_cache=False)
    assert "avg_stock_volume_20d" in snapshot.missing_reasons
    assert "hist" in snapshot.missing_reasons["avg_stock_volume_20d"].lower() or "insufficient" in snapshot.missing_reasons["avg_stock_volume_20d"].lower()
    assert snapshot.avg_stock_volume_20d is None
    # Stage1 BLOCK when required: avg_stock_volume_20d is not in REQUIRED_STAGE1_FIELDS today; if it were, evaluate_stage1 would BLOCK (covered by test_stage1_blocks_on_missing_required).
    assert "avg_stock_volume_20d" not in REQUIRED_STAGE1_FIELDS
