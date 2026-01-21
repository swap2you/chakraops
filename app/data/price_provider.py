
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Provider interface for fetching historical daily price data."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class PriceProvider(Protocol):
    """Interface for price data providers.

    Implementations must return a ``pandas.DataFrame`` with daily bars
    ordered from oldest to newest (ascending by date).
    """

    def get_daily(self, symbol: str, lookback: int = 400) -> pd.DataFrame:
        """Fetch daily bars for the given symbol.

        Parameters
        ----------
        symbol:
            Ticker symbol to fetch (e.g., ``"SPY"``).
        lookback:
            Maximum number of most-recent daily bars to return. Providers
            may return fewer rows if less data is available.

        Returns
        -------
        pandas.DataFrame
            Columns: ``date`` (datetime), ``open``, ``high``, ``low``,
            ``close``, ``volume``. Rows are sorted ascending by ``date``
            so the newest observation is last.
        """
        ...


__all__ = ["PriceProvider"]