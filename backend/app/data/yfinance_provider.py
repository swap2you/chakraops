# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""yfinance price provider implementation (fallback)."""

from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore

from .price_provider import PriceProvider


class YFinanceProvider(PriceProvider):
    """Fetch daily OHLCV bars from yfinance as a fallback provider."""

    def __init__(self) -> None:
        """Initialize yfinance provider."""
        if yf is None:
            raise ImportError(
                "yfinance is not installed. "
                "Install it with: pip install yfinance\n"
                "Or use PolygonProvider instead."
            )

    def get_daily(self, symbol: str, lookback: int = 400) -> pd.DataFrame:
        """Return daily OHLCV bars for ``symbol`` with newest rows last."""
        if lookback <= 0:
            raise ValueError("lookback must be positive")

        if yf is None:
            raise RuntimeError("yfinance is not available")

        try:
            ticker = yf.Ticker(symbol)
            # Calculate start date: lookback trading days + buffer for weekends/holidays
            end_date = dt.date.today()
            start_date = end_date - dt.timedelta(days=int(lookback * 1.5))
            
            # Fetch historical data
            hist = ticker.history(start=start_date.isoformat(), end=end_date.isoformat(), auto_adjust=True)
            
            if hist.empty:
                raise ValueError(f"No data returned for {symbol}")
            
        except Exception as exc:
            if isinstance(exc, ValueError):
                raise
            raise ValueError(f"Failed to fetch data for {symbol}: {exc}") from exc

        # Rename columns to match expected format
        df = hist.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        # Ensure date column is datetime
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])

        # Convert date to naive datetime (remove timezone if present)
        if df["date"].dt.tz is not None:
            df["date"] = df["date"].dt.tz_localize(None)

        # Sort by date ascending (newest last)
        df = df.sort_values("date", ascending=True).reset_index(drop=True)

        # Select only required columns and ensure correct order
        df = df[["date", "open", "high", "low", "close", "volume"]]

        # Trim to requested lookback (keep newest rows)
        if len(df) > lookback:
            df = df.tail(lookback).reset_index(drop=True)

        return df


__all__ = ["YFinanceProvider"]
