# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
CSP contract selection: delta magnitude filter and normalized delta (Phase 3.3.2).

- Delta filter uses magnitude: 0.15 <= |delta| <= 0.35 for puts.
- PUT with delta +0.25 or -0.25 are both in-range.
- Normalized delta for reporting: puts negative, calls positive.
- CALLs are excluded from CSP selection (option_type filter).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.models.data_quality import DataQuality, FieldValue
from app.core.options.chain_provider import OptionContract, OptionType, OptionsChain, ChainProviderResult
from app.core.eval.staged_evaluator import (
    _delta_magnitude,
    _normalized_delta,
    _select_csp_candidates,
)


def _make_put(delta_value: float, dte: int = 40) -> OptionContract:
    """OptionContract PUT with given delta (raw; may be + or -)."""
    exp = date.today() + timedelta(days=dte)
    return OptionContract(
        symbol="SPY",
        expiration=exp,
        strike=500.0,
        option_type=OptionType.PUT,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        mid=FieldValue(5.05, DataQuality.VALID, "", "mid"),
        last=FieldValue(5.05, DataQuality.VALID, "", "last"),
        open_interest=FieldValue(1000, DataQuality.VALID, "", "open_interest"),
        volume=FieldValue(50, DataQuality.VALID, "", "volume"),
        delta=FieldValue(delta_value, DataQuality.VALID, "", "delta"),
        gamma=FieldValue(0.02, DataQuality.VALID, "", "gamma"),
        theta=FieldValue(-0.05, DataQuality.VALID, "", "theta"),
        vega=FieldValue(0.10, DataQuality.VALID, "", "vega"),
        iv=FieldValue(0.18, DataQuality.VALID, "", "iv"),
        spread=FieldValue(0.1, DataQuality.VALID, "", "spread"),
        spread_pct=FieldValue(0.02, DataQuality.VALID, "", "spread_pct"),
        dte=dte,
    )


def _make_call(delta_value: float, dte: int = 40) -> OptionContract:
    """OptionContract CALL with given delta."""
    exp = date.today() + timedelta(days=dte)
    return OptionContract(
        symbol="SPY",
        expiration=exp,
        strike=500.0,
        option_type=OptionType.CALL,
        bid=FieldValue(5.0, DataQuality.VALID, "", "bid"),
        ask=FieldValue(5.1, DataQuality.VALID, "", "ask"),
        mid=FieldValue(5.05, DataQuality.VALID, "", "mid"),
        last=FieldValue(5.05, DataQuality.VALID, "", "last"),
        open_interest=FieldValue(1000, DataQuality.VALID, "", "open_interest"),
        volume=FieldValue(50, DataQuality.VALID, "", "volume"),
        delta=FieldValue(delta_value, DataQuality.VALID, "", "delta"),
        gamma=FieldValue(0.02, DataQuality.VALID, "", "gamma"),
        theta=FieldValue(-0.05, DataQuality.VALID, "", "theta"),
        vega=FieldValue(0.10, DataQuality.VALID, "", "vega"),
        iv=FieldValue(0.18, DataQuality.VALID, "", "iv"),
        spread=FieldValue(0.1, DataQuality.VALID, "", "spread"),
        spread_pct=FieldValue(0.02, DataQuality.VALID, "", "spread_pct"),
        dte=dte,
    )


class TestDeltaMagnitude:
    """_delta_magnitude returns abs(delta) for range checks."""

    def test_put_positive_delta_magnitude(self):
        put = _make_put(0.25)
        assert _delta_magnitude(put) == 0.25

    def test_put_negative_delta_magnitude(self):
        put = _make_put(-0.25)
        assert _delta_magnitude(put) == 0.25


class TestNormalizedDelta:
    """Normalized delta: negative for puts, positive for calls."""

    def test_put_positive_raw_normalized_negative(self):
        put = _make_put(0.25)
        assert _normalized_delta(put) is not None
        assert _normalized_delta(put) < 0
        assert _normalized_delta(put) == -0.25

    def test_put_negative_raw_normalized_negative(self):
        put = _make_put(-0.25)
        assert _normalized_delta(put) == -0.25

    def test_call_positive_normalized_positive(self):
        call = _make_call(0.25)
        assert _normalized_delta(call) == 0.25


class TestCspSelectionDeltaRange:
    """_select_csp_candidates uses magnitude; PUT +0.25 and -0.25 both in-range. CALL excluded."""

    def _chains_with_put(self, put: OptionContract) -> dict:
        exp = put.expiration
        chain = OptionsChain(
            symbol="SPY",
            expiration=exp,
            underlying_price=FieldValue(500.0, DataQuality.VALID, "", "underlying_price"),
            contracts=[put],
            fetched_at="2026-02-10T12:00:00Z",
            source="ORATS",
            fetch_duration_ms=100,
        )
        return {exp: ChainProviderResult(success=True, chain=chain)}

    def test_put_with_positive_delta_in_range(self):
        put = _make_put(0.25)
        put.compute_derived_fields()
        chains = self._chains_with_put(put)
        candidates, reasons, counts, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert len(candidates) >= 1, "PUT with delta +0.25 should be in delta range"
        assert candidates[0].contract.option_type == OptionType.PUT
        assert _normalized_delta(candidates[0].contract) == -0.25

    def test_put_with_negative_delta_in_range(self):
        put = _make_put(-0.25)
        put.compute_derived_fields()
        chains = self._chains_with_put(put)
        candidates, reasons, counts, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert len(candidates) >= 1, "PUT with delta -0.25 should be in delta range"
        assert _normalized_delta(candidates[0].contract) == -0.25

    def test_call_with_positive_delta_excluded_from_csp(self):
        call = _make_call(0.25)
        call.compute_derived_fields()
        chains = self._chains_with_put(call)
        candidates, reasons, _, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert len(candidates) == 0, "CALL must be excluded from CSP selection (CSP selects PUTs only)"

    def test_rejection_counts_returned(self):
        put = _make_put(0.10)
        put.compute_derived_fields()
        chains = self._chains_with_put(put)
        _, reasons, counts, _ = _select_csp_candidates(
            chains, dte_min=30, dte_max=45, delta_lo=0.15, delta_hi=0.35,
            min_oi=500, max_spread_pct=0.10, symbol="SPY",
        )
        assert "rejected_due_to_delta" in counts
        assert "rejected_due_to_oi" in counts
        assert "rejected_due_to_spread" in counts
        assert "rejected_due_to_missing_fields" in counts
