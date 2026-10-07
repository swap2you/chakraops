# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Mock options chain provider for testing."""

from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List

from app.data.options_chain_provider import OptionsChainProvider


class MockOptionsChainProvider(OptionsChainProvider):
    """Mock options chain provider that returns deterministic test data."""

    def __init__(self, test_data: Dict[str, List[Dict]]) -> None:
        """Initialize with test data.

        Args:
            test_data: Dict mapping symbol -> list of option chain dicts
                Each dict should have: expiry, strike, right, bid, ask, delta, iv, volume, open_interest
        """
        self._test_data = test_data

    def get_expirations(self, symbol: str) -> List[date]:
        """Return expirations for symbol from test data."""
        symbol_upper = symbol.upper()
        if symbol_upper not in self._test_data:
            return []

        expirations = set()
        for opt in self._test_data[symbol_upper]:
            expiry_str = opt.get("expiry")
            if isinstance(expiry_str, date):
                expirations.add(expiry_str)
            elif isinstance(expiry_str, str):
                # Parse ISO format
                expirations.add(date.fromisoformat(expiry_str))

        return sorted(expirations)

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict]:
        """Return chain for symbol/expiry/right from test data."""
        symbol_upper = symbol.upper()
        right_upper = right.upper()

        if symbol_upper not in self._test_data:
            return []

        chain = []
        for opt in self._test_data[symbol_upper]:
            opt_expiry = opt.get("expiry")
            if isinstance(opt_expiry, str):
                opt_expiry = date.fromisoformat(opt_expiry)
            opt_right = opt.get("right", "").upper()

            if opt_expiry == expiry and opt_right == right_upper:
                chain.append(opt)

        return chain


__all__ = ["MockOptionsChainProvider"]
