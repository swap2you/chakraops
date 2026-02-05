# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for signals utility functions."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.signals.utils import calc_dte, mid, spread_pct


class TestCalcDte:
    """Test calc_dte function."""

    def test_positive_dte(self) -> None:
        """Calculate DTE for future expiration."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        expiry = date(2026, 2, 20)
        assert calc_dte(as_of, expiry) == 29

    def test_same_day(self) -> None:
        """DTE should be 0 for same day expiration."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        expiry = date(2026, 1, 22)
        assert calc_dte(as_of, expiry) == 0

    def test_negative_dte(self) -> None:
        """DTE should be negative for past expiration."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        expiry = date(2026, 1, 20)
        assert calc_dte(as_of, expiry) == -2

    def test_one_day_dte(self) -> None:
        """DTE should be 1 for next day expiration."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        expiry = date(2026, 1, 23)
        assert calc_dte(as_of, expiry) == 1

    def test_long_dte(self) -> None:
        """DTE should handle long expiration periods."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        expiry = date(2026, 12, 31)
        assert calc_dte(as_of, expiry) == 343


class TestMid:
    """Test mid price calculation."""

    def test_normal_bid_ask(self) -> None:
        """Calculate mid from normal bid/ask."""
        assert mid(2.50, 2.60) == 2.55
        assert mid(100.0, 101.0) == 100.5

    def test_bid_none(self) -> None:
        """Mid should be None if bid is None."""
        assert mid(None, 2.60) is None

    def test_ask_none(self) -> None:
        """Mid should be None if ask is None."""
        assert mid(2.50, None) is None

    def test_both_none(self) -> None:
        """Mid should be None if both are None."""
        assert mid(None, None) is None

    def test_bid_zero_ask_zero(self) -> None:
        """Mid should be None if both bid and ask are 0."""
        assert mid(0.0, 0.0) is None

    def test_bid_zero_ask_positive(self) -> None:
        """Mid should be calculated if bid is 0 but ask is positive."""
        assert mid(0.0, 2.60) == 1.30

    def test_bid_positive_ask_zero(self) -> None:
        """Mid should be calculated if ask is 0 but bid is positive."""
        assert mid(2.50, 0.0) == 1.25

    def test_negative_values(self) -> None:
        """Mid should handle negative values (though unusual)."""
        assert mid(-1.0, 1.0) == 0.0
        assert mid(-2.0, -1.0) == -1.5

    def test_identical_bid_ask(self) -> None:
        """Mid should be the same value if bid equals ask."""
        assert mid(2.50, 2.50) == 2.50
        assert mid(100.0, 100.0) == 100.0


class TestSpreadPct:
    """Test spread_pct function."""

    def test_normal_spread(self) -> None:
        """Calculate spread percentage for normal bid/ask."""
        # bid=2.50, ask=2.60, mid=2.55, spread=0.10
        # spread_pct = (0.10 / 2.55) * 100 = 3.9215686274509802
        result = spread_pct(2.50, 2.60)
        assert result is not None
        assert abs(result - 3.9215686274509802) < 0.0001

    def test_tight_spread(self) -> None:
        """Calculate spread percentage for tight spread."""
        # bid=100.00, ask=100.01, mid=100.005, spread=0.01
        # spread_pct = (0.01 / 100.005) * 100 ≈ 0.01
        result = spread_pct(100.00, 100.01)
        assert result is not None
        assert abs(result - 0.0099995) < 0.0001

    def test_wide_spread(self) -> None:
        """Calculate spread percentage for wide spread."""
        # bid=1.00, ask=2.00, mid=1.50, spread=1.00
        # spread_pct = (1.00 / 1.50) * 100 = 66.666...
        result = spread_pct(1.00, 2.00)
        assert result is not None
        assert abs(result - 66.66666666666666) < 0.0001

    def test_bid_none(self) -> None:
        """Spread should be None if bid is None."""
        assert spread_pct(None, 2.60) is None

    def test_ask_none(self) -> None:
        """Spread should be None if ask is None."""
        assert spread_pct(2.50, None) is None

    def test_both_none(self) -> None:
        """Spread should be None if both are None."""
        assert spread_pct(None, None) is None

    def test_both_zero(self) -> None:
        """Spread should be None if both bid and ask are 0."""
        assert spread_pct(0.0, 0.0) is None

    def test_bid_greater_than_ask(self) -> None:
        """Spread should be None if bid > ask (invalid quote)."""
        assert spread_pct(2.60, 2.50) is None
        assert spread_pct(100.0, 50.0) is None

    def test_bid_equals_ask(self) -> None:
        """Spread should be 0 if bid equals ask."""
        result = spread_pct(2.50, 2.50)
        assert result is not None
        assert result == 0.0

    def test_zero_mid_price(self) -> None:
        """Spread should be None if mid price is 0 (division by zero protection)."""
        # This case is handled by the bid==0 and ask==0 check, but test explicitly
        assert spread_pct(0.0, 0.0) is None

    def test_bid_zero_ask_positive(self) -> None:
        """Spread should be calculated if bid is 0 but ask is positive."""
        # bid=0, ask=2.60, mid=1.30, spread=2.60
        # spread_pct = (2.60 / 1.30) * 100 = 200.0
        result = spread_pct(0.0, 2.60)
        assert result is not None
        assert abs(result - 200.0) < 0.0001

    def test_very_small_values(self) -> None:
        """Spread should handle very small bid/ask values."""
        result = spread_pct(0.001, 0.002)
        assert result is not None
        # mid=0.0015, spread=0.001, spread_pct = (0.001 / 0.0015) * 100 ≈ 66.67
        assert abs(result - 66.66666666666666) < 0.0001

    def test_very_large_values(self) -> None:
        """Spread should handle very large bid/ask values."""
        result = spread_pct(1000.0, 1001.0)
        assert result is not None
        # mid=1000.5, spread=1.0, spread_pct = (1.0 / 1000.5) * 100 ≈ 0.09995
        assert abs(result - 0.09995002498750625) < 0.0001

    def test_negative_bid_ask(self) -> None:
        """Spread should return None when mid price is 0 (e.g., negative bid, positive ask)."""
        # mid(-1.0, 1.0) = 0.0, so spread_pct should return None to avoid division by zero
        assert spread_pct(-1.0, 1.0) is None

    def test_edge_case_bid_slightly_greater(self) -> None:
        """Spread should be None if bid is even slightly greater than ask."""
        assert spread_pct(2.5001, 2.5000) is None
        assert spread_pct(100.0001, 100.0) is None


class TestUtilsIntegration:
    """Integration tests for utility functions."""

    def test_mid_and_spread_consistency(self) -> None:
        """Mid and spread_pct should be consistent."""
        bid = 2.50
        ask = 2.60
        mid_price = mid(bid, ask)
        spread = spread_pct(bid, ask)

        assert mid_price is not None
        assert spread is not None

        # Verify spread calculation matches expected formula
        expected_spread = ((ask - bid) / mid_price) * 100.0
        assert abs(spread - expected_spread) < 0.0001

    def test_realistic_option_quote(self) -> None:
        """Test with realistic option quote values."""
        bid = 2.50
        ask = 2.60
        mid_price = mid(bid, ask)
        spread = spread_pct(bid, ask)

        assert mid_price == 2.55
        assert spread is not None
        assert spread > 0
        assert spread < 10  # Reasonable spread for liquid options

    def test_zero_bid_scenarios(self) -> None:
        """Test various scenarios with zero bid."""
        # Zero bid, positive ask
        assert mid(0.0, 2.60) == 1.30
        spread = spread_pct(0.0, 2.60)
        assert spread is not None
        assert spread == 200.0  # 100% spread when bid is 0

        # Zero bid, zero ask
        assert mid(0.0, 0.0) is None
        assert spread_pct(0.0, 0.0) is None


__all__ = [
    "TestCalcDte",
    "TestMid",
    "TestSpreadPct",
    "TestUtilsIntegration",
]
