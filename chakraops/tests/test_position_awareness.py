# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 9: Position-aware evaluation and exposure control tests."""

import pytest
from unittest.mock import MagicMock, patch

from app.core.eval.position_awareness import (
    get_open_positions_by_symbol,
    has_open_csp,
    has_open_cc,
    position_blocks_new_csp,
    position_blocks_new_cc,
    position_blocks_recommendation,
    get_exposure_summary,
    check_exposure_limits,
    ExposureSummary,
)


class TestPositionBlocks:
    """CSP/CC blocking rules."""

    def test_position_blocks_new_csp_when_open_csp(self):
        """If open CSP exists for symbol, block new CSP."""
        by_symbol = {"AAPL": [MagicMock(strategy="CSP", remaining_qty=1)]}
        assert position_blocks_new_csp("AAPL", by_symbol) is True
        assert position_blocks_new_csp("MSFT", by_symbol) is False

    def test_position_blocks_new_cc_when_open_cc(self):
        """If open CC exists for symbol, block new CC."""
        by_symbol = {"GOOGL": [MagicMock(strategy="CC", remaining_qty=1)]}
        assert position_blocks_new_cc("GOOGL", by_symbol) is True
        assert position_blocks_new_cc("AAPL", by_symbol) is False

    def test_position_blocks_recommendation_csp_focus(self):
        """For CSP focus: block when open CSP or open CC."""
        by_symbol = {"AAPL": [MagicMock(strategy="CSP", remaining_qty=1)]}
        blocks, reason = position_blocks_recommendation("AAPL", by_symbol, strategy_focus="CSP")
        assert blocks is True
        assert reason == "POSITION_ALREADY_OPEN"

        by_symbol_cc = {"MSFT": [MagicMock(strategy="CC", remaining_qty=1)]}
        blocks2, reason2 = position_blocks_recommendation("MSFT", by_symbol_cc, strategy_focus="CSP")
        assert blocks2 is True
        assert reason2 == "POSITION_ALREADY_OPEN"

    def test_position_blocks_recommendation_no_position(self):
        """When no open position, do not block."""
        by_symbol = {"AAPL": []}
        blocks, reason = position_blocks_recommendation("AAPL", by_symbol, strategy_focus="CSP")
        assert blocks is False
        assert reason == ""


class TestExposureSummary:
    """Exposure summary and limits."""

    def test_exposure_summary_empty(self):
        """Empty open positions -> total_positions 0."""
        summary = get_exposure_summary(open_trades_by_symbol={})
        assert summary.total_positions == 0
        assert summary.by_symbol == {}
        assert summary.at_cap is False

    def test_exposure_summary_by_symbol(self):
        """Multiple symbols with open positions."""
        t1 = MagicMock(remaining_qty=2)
        t1.strategy = "CSP"
        by_symbol = {
            "AAPL": [t1],
            "MSFT": [MagicMock(strategy="CC", remaining_qty=1)],
        }
        summary = get_exposure_summary(open_trades_by_symbol=by_symbol)
        assert summary.total_positions == 2
        assert "AAPL" in summary.by_symbol
        assert "MSFT" in summary.by_symbol
        assert summary.by_symbol["AAPL"]["strategies"] == ["CSP"]

    def test_exposure_cap_at_max(self):
        """When total_positions >= max_concurrent_positions, at_cap is True."""
        portfolio_config = {"max_active_positions": 2}
        by_symbol = {
            "A": [MagicMock(strategy="CSP", remaining_qty=1)],
            "B": [MagicMock(strategy="CSP", remaining_qty=1)],
        }
        summary = get_exposure_summary(open_trades_by_symbol=by_symbol, portfolio_config=portfolio_config)
        assert summary.total_positions == 2
        assert summary.max_concurrent_positions == 2
        assert summary.at_cap is True

    def test_check_exposure_limits_at_cap_new_symbol(self):
        """When at cap and symbol has no position, not allowed (EXPOSURE_CAP)."""
        summary = ExposureSummary(
            total_positions=5,
            by_symbol={"AAPL": {}, "MSFT": {}},
            max_concurrent_positions=5,
            at_cap=True,
            symbols_over_capital_cap=[],
        )
        allowed, reason = check_exposure_limits("GOOGL", summary)
        assert allowed is False
        assert reason == "EXPOSURE_CAP"

    def test_check_exposure_limits_at_cap_existing_position(self):
        """When at cap but symbol already has position, allowed (evaluation continues)."""
        summary = ExposureSummary(
            total_positions=5,
            by_symbol={"AAPL": {"position_count": 1}},
            max_concurrent_positions=5,
            at_cap=True,
            symbols_over_capital_cap=[],
        )
        allowed, reason = check_exposure_limits("AAPL", summary)
        assert allowed is True
        assert reason == ""
