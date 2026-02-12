# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for signals package: sorting determinism and model immutability."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.signals.models import (
    ExclusionReason,
    ExplanationItem,
    SignalCandidate,
    SignalType,
)


class TestModelImmutability:
    """Test that signal models are immutable (frozen dataclasses)."""

    def test_signal_candidate_is_immutable(self) -> None:
        """SignalCandidate should be immutable (frozen dataclass)."""
        candidate = SignalCandidate(
            symbol="AAPL",
            signal_type=SignalType.CSP,
            as_of=datetime(2026, 1, 22, 10, 0, 0),
            underlying_price=150.0,
            expiry=date(2026, 2, 20),
            strike=145.0,
            option_right="PUT",
            bid=2.50,
            ask=2.60,
            mid=2.55,
            volume=1000,
            open_interest=5000,
        )

        # Attempting to modify should raise AttributeError
        with pytest.raises(AttributeError):
            candidate.symbol = "MSFT"  # type: ignore

        with pytest.raises(AttributeError):
            candidate.strike = 150.0  # type: ignore

    def test_explanation_item_is_immutable(self) -> None:
        """ExplanationItem should be immutable."""
        item = ExplanationItem(
            code="HIGH_IV",
            message="IV rank is above threshold",
            data={"iv_rank": 0.85},
        )

        with pytest.raises(AttributeError):
            item.code = "LOW_IV"  # type: ignore

    def test_exclusion_reason_is_immutable(self) -> None:
        """ExclusionReason should be immutable."""
        reason = ExclusionReason(
            code="PRICE_OUT_OF_RANGE",
            message="Price is outside allowed range",
            data={"price": 1000.0, "max_price": 500.0},
        )

        with pytest.raises(AttributeError):
            reason.code = "OTHER"  # type: ignore


class TestSortingDeterminism:
    """Test that signal candidates sort deterministically."""

    def test_sort_by_symbol_signal_type_expiry_strike(self) -> None:
        """Candidates should sort by (symbol, signal_type, expiry, strike)."""
        base_time = datetime(2026, 1, 22, 10, 0, 0)

        candidates = [
            SignalCandidate(
                symbol="MSFT",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=400.0,
                expiry=date(2026, 2, 20),
                strike=390.0,
                option_right="PUT",
                bid=5.0,
                ask=5.2,
                mid=5.1,
            ),
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CC,
                as_of=base_time,
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=155.0,
                option_right="CALL",
                bid=3.0,
                ask=3.2,
                mid=3.1,
            ),
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=145.0,
                option_right="PUT",
                bid=2.5,
                ask=2.6,
                mid=2.55,
            ),
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=150.0,
                expiry=date(2026, 3, 20),
                strike=145.0,
                option_right="PUT",
                bid=3.0,
                ask=3.1,
                mid=3.05,
            ),
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=140.0,
                option_right="PUT",
                bid=2.0,
                ask=2.1,
                mid=2.05,
            ),
        ]

        # Sort deterministically
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                c.symbol,
                c.signal_type.value,
                c.expiry,
                c.strike,
            ),
        )

        # Verify sort order (alphabetical: CC < CSP)
        assert sorted_candidates[0].symbol == "AAPL"
        assert sorted_candidates[0].signal_type == SignalType.CC
        assert sorted_candidates[0].expiry == date(2026, 2, 20)
        assert sorted_candidates[0].strike == 155.0

        assert sorted_candidates[1].symbol == "AAPL"
        assert sorted_candidates[1].signal_type == SignalType.CSP
        assert sorted_candidates[1].expiry == date(2026, 2, 20)
        assert sorted_candidates[1].strike == 140.0

        assert sorted_candidates[2].symbol == "AAPL"
        assert sorted_candidates[2].signal_type == SignalType.CSP
        assert sorted_candidates[2].expiry == date(2026, 2, 20)
        assert sorted_candidates[2].strike == 145.0

        assert sorted_candidates[3].symbol == "AAPL"
        assert sorted_candidates[3].signal_type == SignalType.CSP
        assert sorted_candidates[3].expiry == date(2026, 3, 20)
        assert sorted_candidates[3].strike == 145.0

        assert sorted_candidates[4].symbol == "MSFT"
        assert sorted_candidates[4].signal_type == SignalType.CSP

    def test_sort_is_deterministic_multiple_passes(self) -> None:
        """Sorting should produce the same result on multiple passes."""
        base_time = datetime(2026, 1, 22, 10, 0, 0)

        candidates = [
            SignalCandidate(
                symbol="B",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=100.0,
                expiry=date(2026, 2, 20),
                strike=95.0,
                option_right="PUT",
                bid=2.0,
                ask=2.1,
                mid=2.05,
            ),
            SignalCandidate(
                symbol="A",
                signal_type=SignalType.CC,
                as_of=base_time,
                underlying_price=50.0,
                expiry=date(2026, 2, 20),
                strike=55.0,
                option_right="CALL",
                bid=1.0,
                ask=1.1,
                mid=1.05,
            ),
            SignalCandidate(
                symbol="C",
                signal_type=SignalType.CSP,
                as_of=base_time,
                underlying_price=200.0,
                expiry=date(2026, 2, 20),
                strike=195.0,
                option_right="PUT",
                bid=3.0,
                ask=3.1,
                mid=3.05,
            ),
        ]

        # Sort multiple times
        sort_key = lambda c: (c.symbol, c.signal_type.value, c.expiry, c.strike)
        sorted1 = sorted(candidates, key=sort_key)
        sorted2 = sorted(candidates, key=sort_key)
        sorted3 = sorted(candidates, key=sort_key)

        # All should be identical
        assert sorted1 == sorted2 == sorted3

        # Verify order is consistent
        assert [c.symbol for c in sorted1] == ["A", "B", "C"]
        assert [c.signal_type for c in sorted1] == [SignalType.CC, SignalType.CSP, SignalType.CSP]


class TestSignalCandidateValidation:
    """Test SignalCandidate validation rules."""

    def test_csp_must_use_put(self) -> None:
        """CSP signals must use PUT options."""
        with pytest.raises(ValueError, match="CSP signals must use PUT options"):
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CSP,
                as_of=datetime(2026, 1, 22, 10, 0, 0),
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=155.0,
                option_right="CALL",  # Wrong for CSP
                bid=3.0,
                ask=3.2,
                mid=3.1,
            )

    def test_cc_must_use_call(self) -> None:
        """CC signals must use CALL options."""
        with pytest.raises(ValueError, match="CC signals must use CALL options"):
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CC,
                as_of=datetime(2026, 1, 22, 10, 0, 0),
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=145.0,
                option_right="PUT",  # Wrong for CC
                bid=2.5,
                ask=2.6,
                mid=2.55,
            )

    def test_option_right_must_be_put_or_call(self) -> None:
        """option_right must be PUT or CALL."""
        with pytest.raises(ValueError, match="option_right must be PUT or CALL"):
            SignalCandidate(
                symbol="AAPL",
                signal_type=SignalType.CSP,
                as_of=datetime(2026, 1, 22, 10, 0, 0),
                underlying_price=150.0,
                expiry=date(2026, 2, 20),
                strike=145.0,
                option_right="INVALID",  # type: ignore
                bid=2.5,
                ask=2.6,
                mid=2.55,
            )


__all__ = [
    "TestModelImmutability",
    "TestSortingDeterminism",
    "TestSignalCandidateValidation",
]
