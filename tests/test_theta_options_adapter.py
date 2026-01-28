# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Theta options adapter: normalization and parsing."""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.signals.adapters.theta_options_adapter import (
    NormalizedOptionQuote,
    normalize_theta_chain,
)
from app.signals.models import ExclusionReason


def get_fixture_path() -> Path:
    """Get path to test fixture JSON file."""
    return Path(__file__).parent / "fixtures" / "theta_chain_sample.json"


def load_fixture() -> list[dict]:
    """Load test fixture JSON."""
    with open(get_fixture_path(), "r") as f:
        return json.load(f)


class TestNormalizedOptionQuote:
    """Test NormalizedOptionQuote model."""

    def test_quote_is_immutable(self) -> None:
        """NormalizedOptionQuote should be immutable."""
        quote = NormalizedOptionQuote(
            underlying="AAPL",
            expiry=date(2026, 2, 20),
            strike=Decimal("145.0"),
            right="PUT",
            bid=2.50,
            ask=2.60,
            last=2.55,
            volume=1000,
            open_interest=5000,
            as_of=datetime(2026, 1, 22, 10, 0, 0),
        )

        with pytest.raises(AttributeError):
            quote.strike = Decimal("150.0")  # type: ignore

    def test_right_validation(self) -> None:
        """NormalizedOptionQuote should validate right field."""
        with pytest.raises(ValueError, match="right must be PUT or CALL"):
            NormalizedOptionQuote(
                underlying="AAPL",
                expiry=date(2026, 2, 20),
                strike=Decimal("145.0"),
                right="INVALID",  # type: ignore
                bid=2.50,
                ask=2.60,
                last=None,
                volume=None,
                open_interest=None,
                as_of=datetime(2026, 1, 22, 10, 0, 0),
            )


class TestNormalizeThetaChain:
    """Test normalize_theta_chain function."""

    def test_deterministic_output_ordering(self) -> None:
        """Normalized quotes should be sorted by (expiry, strike, right)."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-03-20",
                "strike": 150.0,
                "right": "PUT",
                "bid": 4.0,
                "ask": 4.2,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 155.0,
                "right": "CALL",
                "bid": 3.0,
                "ask": 3.2,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "right": "PUT",
                "bid": 2.5,
                "ask": 2.6,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 150.0,
                "right": "PUT",
                "bid": 3.0,
                "ask": 3.1,
            },
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        # Should have 4 valid quotes
        assert len(normalized) == 4
        assert len(exclusions) == 0

        # Verify sort order: (expiry, strike, right)
        assert normalized[0].expiry == date(2026, 2, 20)
        assert normalized[0].strike == Decimal("145.0")
        assert normalized[0].right == "PUT"

        assert normalized[1].expiry == date(2026, 2, 20)
        assert normalized[1].strike == Decimal("150.0")
        assert normalized[1].right == "PUT"

        assert normalized[2].expiry == date(2026, 2, 20)
        assert normalized[2].strike == Decimal("155.0")
        assert normalized[2].right == "CALL"

        assert normalized[3].expiry == date(2026, 3, 20)
        assert normalized[3].strike == Decimal("150.0")
        assert normalized[3].right == "PUT"

    def test_deterministic_multiple_passes(self) -> None:
        """Normalization should produce identical results on multiple passes."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "right": "PUT",
                "bid": 2.5,
                "ask": 2.6,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 150.0,
                "right": "CALL",
                "bid": 3.0,
                "ask": 3.2,
            },
        ]

        result1 = normalize_theta_chain(chain, as_of, underlying="AAPL")
        result2 = normalize_theta_chain(chain, as_of, underlying="AAPL")
        result3 = normalize_theta_chain(chain, as_of, underlying="AAPL")

        # All results should be identical
        assert result1 == result2 == result3

        # Verify quotes are sorted consistently
        quotes1 = result1[0]
        quotes2 = result2[0]
        assert [q.strike for q in quotes1] == [q.strike for q in quotes2]

    def test_exclusions_for_invalid_rows(self) -> None:
        """Invalid rows should produce ExclusionReason entries."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            # Valid row
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "right": "PUT",
                "bid": 2.5,
                "ask": 2.6,
            },
            # Missing expiry
            {
                "symbol": "AAPL",
                "strike": 150.0,
                "right": "PUT",
            },
            # Missing strike
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "right": "PUT",
            },
            # Invalid strike
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": "not_a_number",
                "right": "PUT",
            },
            # Invalid expiry
            {
                "symbol": "AAPL",
                "expiry": "invalid-date",
                "strike": 150.0,
                "right": "PUT",
            },
            # Invalid right
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 150.0,
                "right": "INVALID",
            },
            # Not a dict
            "not_a_dict",
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        # Should have 1 valid quote
        assert len(normalized) == 1
        assert normalized[0].underlying == "AAPL"
        assert normalized[0].strike == Decimal("145.0")

        # Should have 6 exclusions
        assert len(exclusions) == 6
        assert all(ex.code == "UNPARSABLE_OPTION_ROW" for ex in exclusions)

        # Verify exclusion reasons contain row_index
        exclusion_indices = {ex.data.get("row_index") for ex in exclusions}
        assert exclusion_indices == {1, 2, 3, 4, 5, 6}

    def test_fixture_parsing(self) -> None:
        """Test parsing with real fixture data."""
        fixture_data = load_fixture()
        as_of = datetime(2026, 1, 22, 10, 0, 0)

        normalized, exclusions = normalize_theta_chain(fixture_data, as_of)

        # Fixture has 4 valid rows (rows 0-3) and 6 invalid rows (rows 4-9)
        assert len(normalized) == 4
        assert len(exclusions) == 6

        # Verify valid quotes are sorted
        assert all(isinstance(q, NormalizedOptionQuote) for q in normalized)
        assert normalized[0].expiry <= normalized[1].expiry
        if normalized[0].expiry == normalized[1].expiry:
            assert normalized[0].strike <= normalized[1].strike

        # Verify exclusions have proper structure
        assert all(isinstance(ex, ExclusionReason) for ex in exclusions)
        assert all(ex.code == "UNPARSABLE_OPTION_ROW" for ex in exclusions)
        assert all("row_index" in ex.data for ex in exclusions)

    def test_optional_fields_handled_gracefully(self) -> None:
        """Missing optional fields should not cause exclusions."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "right": "PUT",
                # No bid/ask/volume/etc - should still parse
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 150.0,
                "right": "CALL",
                "bid": None,
                "ask": None,
                "volume": None,
            },
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        assert len(normalized) == 2
        assert len(exclusions) == 0

        # Optional fields should be None
        assert normalized[0].bid is None
        assert normalized[0].ask is None
        assert normalized[0].volume is None
        assert normalized[0].open_interest is None

    def test_right_normalization(self) -> None:
        """Test that right field is normalized correctly."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.0,
                "right": "P",  # Should normalize to PUT
                "bid": 2.5,
                "ask": 2.6,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 150.0,
                "right": "C",  # Should normalize to CALL
                "bid": 3.0,
                "ask": 3.2,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 155.0,
                "right": "PUTS",  # Should normalize to PUT
                "bid": 4.0,
                "ask": 4.2,
            },
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        assert len(normalized) == 3
        assert normalized[0].right == "PUT"
        assert normalized[1].right == "CALL"
        assert normalized[2].right == "PUT"

    def test_expiry_format_variations(self) -> None:
        """Test parsing different expiry formats."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",  # ISO format
                "strike": 145.0,
                "right": "PUT",
                "bid": 2.5,
                "ask": 2.6,
            },
            {
                "symbol": "AAPL",
                "expiry": "20260220",  # YYYYMMDD format
                "strike": 150.0,
                "right": "PUT",
                "bid": 3.0,
                "ask": 3.2,
            },
            {
                "symbol": "AAPL",
                "expiration": "2026-03-20",  # Alternative key name
                "strike": 155.0,
                "right": "PUT",
                "bid": 4.0,
                "ask": 4.2,
            },
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        assert len(normalized) == 3
        assert normalized[0].expiry == date(2026, 2, 20)
        assert normalized[1].expiry == date(2026, 2, 20)
        assert normalized[2].expiry == date(2026, 3, 20)

    def test_strike_as_decimal(self) -> None:
        """Test that strike is stored as Decimal."""
        as_of = datetime(2026, 1, 22, 10, 0, 0)
        chain = [
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": 145.5,  # Float
                "right": "PUT",
                "bid": 2.5,
                "ask": 2.6,
            },
            {
                "symbol": "AAPL",
                "expiry": "2026-02-20",
                "strike": "150.0",  # String
                "right": "PUT",
                "bid": 3.0,
                "ask": 3.2,
            },
        ]

        normalized, exclusions = normalize_theta_chain(chain, as_of, underlying="AAPL")

        assert len(normalized) == 2
        assert isinstance(normalized[0].strike, Decimal)
        assert isinstance(normalized[1].strike, Decimal)
        assert normalized[0].strike == Decimal("145.5")
        assert normalized[1].strike == Decimal("150.0")


__all__ = [
    "TestNormalizedOptionQuote",
    "TestNormalizeThetaChain",
]
