# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""YFinance provider (FALLBACK). Underlying prices only; option_chain_available=False."""

from __future__ import annotations

import logging
from typing import Dict, List

from app.market.providers.base import MarketDataProviderInterface

logger = logging.getLogger(__name__)


class YFinanceProvider(MarketDataProviderInterface):
    """Fallback: yfinance for underlying prices only. No options/Greeks."""

    def __init__(self) -> None:
        try:
            import yfinance as yf  # noqa: F401
        except ImportError:
            self._yf = None
        else:
            self._yf = True

    def health_check(self) -> tuple[bool, str]:
        if self._yf is None:
            return False, "yfinance not installed"
        try:
            import yfinance as yf
            t = yf.Ticker("SPY")
            h = t.history(period="5d")
            if h.empty:
                return False, "yfinance no data"
            return True, "yfinance OK (stocks only)"
        except Exception as e:
            return False, f"yfinance: {e}"

    def fetch_underlying_prices(self, symbols: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        if self._yf is None:
            return out
        try:
            import yfinance as yf
            for symbol in symbols:
                if not symbol or not isinstance(symbol, str):
                    continue
                try:
                    t = yf.Ticker(symbol)
                    h = t.history(period="5d")
                    if not h.empty and "Close" in h.columns:
                        out[symbol] = float(h["Close"].iloc[-1])
                except Exception as e:
                    logger.debug("yfinance price %s: %s", symbol, e)
        except Exception as e:
            logger.warning("yfinance fetch_underlying_prices: %s", e)
        return out

    def fetch_option_chain_availability(self, symbols: List[str]) -> Dict[str, bool]:
        """Never claim option chain available."""
        return {s: False for s in symbols if s and isinstance(s, str)}


__all__ = ["YFinanceProvider"]
