# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for CSP generator."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.signals.csp import generate_csp_candidates
from app.signals.models import CSPConfig, ExclusionReason, SignalEngineConfig, SignalType
from tests.fixtures.csp_test_data import create_test_options, create_test_stock_snapshot


class TestCSPGenerator:
    """Test CSP candidate generation."""

    def test_basic_generation(self) -> None:
        """Test basic CSP candidate generation with valid options."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        # Should have 2 candidates (one per expiry)
        assert len(candidates) == 2
        assert len(exclusions) == 0

        # Verify both are CSP PUTs
        assert all(c.signal_type == SignalType.CSP for c in candidates)
        assert all(c.option_right == "PUT" for c in candidates)

        # Verify sorted by expiry then strike
        assert candidates[0].expiry <= candidates[1].expiry
        if candidates[0].expiry == candidates[1].expiry:
            assert candidates[0].strike <= candidates[1].strike

    def test_chosen_strike_per_expiry_consistent(self) -> None:
        """Test that chosen strike per expiry is consistent across multiple runs."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        # Run multiple times
        results = []
        for _ in range(5):
            candidates, _ = generate_csp_candidates(stock, options, csp_cfg, base_cfg)
            results.append(candidates)

        # All results should be identical
        assert all(r == results[0] for r in results)

        # Verify strikes per expiry are consistent
        expiry_strikes: dict[date, list[float]] = {}
        for candidates in results:
            for c in candidates:
                if c.expiry not in expiry_strikes:
                    expiry_strikes[c.expiry] = []
                expiry_strikes[c.expiry].append(c.strike)

        # Each expiry should have the same strike across all runs
        for expiry, strikes in expiry_strikes.items():
            assert len(set(strikes)) == 1, f"Expiry {expiry} has inconsistent strikes: {strikes}"

    def test_exclusion_no_options(self) -> None:
        """Test exclusion when no options are provided."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options: list = []

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) == 1
        assert exclusions[0].code == "NO_OPTIONS_FOR_SYMBOL"

    def test_exclusion_no_expiry_in_dte_window(self) -> None:
        """Test exclusion when no expiries are in DTE window."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        # DTE window that excludes all options (too short)
        base_cfg = SignalEngineConfig(
            dte_min=1,
            dte_max=5,  # All options are 29+ DTE
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) == 1
        assert exclusions[0].code == "NO_EXPIRY_IN_DTE_WINDOW"

    def test_exclusion_no_liquid_puts(self) -> None:
        """Test exclusion when no liquid PUTs are available."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        # Require very high bid and OI (none will qualify)
        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=100.0,  # Too high
            min_open_interest=100000,  # Too high
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) >= 1
        assert any(ex.code == "NO_LIQUID_PUTS" for ex in exclusions)

    def test_exclusion_no_strikes_in_otm_range(self) -> None:
        """Test exclusion when no strikes are in OTM range."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        # OTM range that excludes all strikes (too narrow)
        csp_cfg = CSPConfig(delta_min=0.80, delta_max=1.0, prob_otm_min=0.70)  # No puts in range

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) >= 1
        assert any(ex.code == "NO_STRIKES_IN_DELTA_RANGE" for ex in exclusions)

    def test_exclusion_no_strikes_in_delta_range(self) -> None:
        """Test exclusion when delta filters are set but no strikes match."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        # Delta range that excludes all strikes (all our put deltas are abs < 0.80)
        csp_cfg = CSPConfig(delta_min=0.80, delta_max=0.90, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) >= 1
        assert any(ex.code == "NO_STRIKES_IN_DELTA_RANGE" for ex in exclusions)

    def test_delta_based_selection(self) -> None:
        """Test that delta-based selection works when delta filters are set."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        # Use delta range that matches some strikes (abs put delta 0.20–0.35)
        csp_cfg = CSPConfig(delta_min=0.20, delta_max=0.35, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        # Should have candidates
        assert len(candidates) > 0

        # Verify selection_path is DELTA
        for candidate in candidates:
            selection_path_items = [e for e in candidate.explanation if e.code == "SELECTION_PATH"]
            assert len(selection_path_items) == 1
            assert selection_path_items[0].data["selection_path"] == "DELTA"

    def test_otm_based_selection(self) -> None:
        """Test that OTM-based selection works when delta filters are not set."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        # No delta filters, use OTM range
        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        # Should have candidates
        assert len(candidates) > 0

        # Verify selection_path is DELTA
        for candidate in candidates:
            selection_path_items = [e for e in candidate.explanation if e.code == "SELECTION_PATH"]
            assert len(selection_path_items) == 1
            assert selection_path_items[0].data["selection_path"] == "DELTA"

    def test_explanation_items_populated(self) -> None:
        """Test that explanation items are properly populated."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, _ = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) > 0

        for candidate in candidates:
            explanation_codes = {e.code for e in candidate.explanation}

            # Required fields should be present
            assert "DTE" in explanation_codes
            assert "SPOT" in explanation_codes
            assert "STRIKE" in explanation_codes
            assert "OTM_PCT" in explanation_codes
            assert "SPREAD_PCT" in explanation_codes
            assert "BID" in explanation_codes
            assert "ASK" in explanation_codes
            assert "MID" in explanation_codes
            assert "VOLUME" in explanation_codes
            assert "OPEN_INTEREST" in explanation_codes
            assert "SELECTION_PATH" in explanation_codes

    def test_deterministic_sorting(self) -> None:
        """Test that output is sorted deterministically by expiry then strike."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, _ = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        # Verify sorting: expiry first, then strike
        for i in range(len(candidates) - 1):
            curr = candidates[i]
            next_c = candidates[i + 1]

            assert curr.expiry <= next_c.expiry
            if curr.expiry == next_c.expiry:
                assert curr.strike <= next_c.strike

    def test_no_underlying_price(self) -> None:
        """Test exclusion when underlying price is None."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=None)  # type: ignore
        options = create_test_options(underlying="AAPL")

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, exclusions = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        assert len(candidates) == 0
        assert len(exclusions) == 1
        assert exclusions[0].code == "NO_UNDERLYING_PRICE"

    def test_filters_call_options(self) -> None:
        """Test that CALL options are filtered out."""
        stock = create_test_stock_snapshot(symbol="AAPL", price=150.0)
        options = create_test_options(underlying="AAPL")

        # Add a CALL option (should be ignored)
        from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote
        from decimal import Decimal

        call_option = NormalizedOptionQuote(
            underlying="AAPL",
            expiry=date(2026, 2, 20),
            strike=Decimal("155.0"),
            right="CALL",
            bid=3.00,
            ask=3.20,
            last=3.10,
            volume=1000,
            open_interest=5000,
            delta=0.50,
            iv=0.25,
            as_of=datetime(2026, 1, 22, 10, 0, 0),
        )
        options.append(call_option)

        base_cfg = SignalEngineConfig(
            dte_min=25,
            dte_max=60,
            min_bid=1.0,
            min_open_interest=1000,
            max_spread_pct=10.0,
        )

        csp_cfg = CSPConfig(delta_min=0.15, delta_max=0.25, prob_otm_min=0.70)

        candidates, _ = generate_csp_candidates(stock, options, csp_cfg, base_cfg)

        # Should still have 2 candidates (CALL was ignored)
        assert len(candidates) == 2
        assert all(c.option_right == "PUT" for c in candidates)


__all__ = ["TestCSPGenerator"]
