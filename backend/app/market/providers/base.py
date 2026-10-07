# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market data provider interface for Phase 8.3 live feed."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class MarketDataProviderInterface(ABC):
    """Interface for live market data providers. Health-check and batch fetch."""

    @abstractmethod
    def health_check(self) -> Tuple[bool, str]:
        """Check if provider is reachable. Do not raise.

        Returns:
            (ok, detail): ok True if usable, detail short message for UI/log.
        """
        ...

    @abstractmethod
    def fetch_underlying_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Fetch current underlying prices for symbols. Missing/errors => omit from dict."""
        ...

    @abstractmethod
    def fetch_option_chain_availability(self, symbols: List[str]) -> Dict[str, bool]:
        """Return per-symbol whether option chain is available. False if not supported."""
        ...

    def fetch_iv_greeks(
        self,
        symbol: str,
        expiry: Optional[str] = None,
        strikes: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """Optional: fetch IV/Greeks for symbol. Default: return empty (not supported)."""
        return {}


__all__ = ["MarketDataProviderInterface"]
