
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Polygon price provider implementation.

DEPRECATED: This provider is deprecated in favor of ThetaDataProvider.
Use app.core.market_data.factory.get_market_data_provider() instead.
This file is kept for backward compatibility only.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from .price_provider import PriceProvider

_NY_TZ = ZoneInfo("America/New_York")


class PolygonProvider(PriceProvider):
    """Fetch daily OHLCV bars from Polygon.io aggregates endpoint."""

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None) -> None:
        """
        Parameters
        ----------
        api_key:
            Polygon API key. If not provided, uses ``POLYGON_API_KEY`` from the environment.
        session:
            Optional ``requests.Session`` for connection reuse/testing.
        """
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise ValueError("POLYGON_API_KEY is not set. Please set it in your environment.")
        self.session = session or requests.Session()

    def get_daily(self, symbol: str, lookback: int = 400) -> pd.DataFrame:
        """Return daily OHLCV bars for ``symbol`` with newest rows last."""
        if lookback <= 0:
            raise ValueError("lookback must be positive")

        end_date = dt.date.today()
        # Request extra days to account for weekends/holidays.
        start_date = end_date - dt.timedelta(days=lookback * 2)

        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/1/day/"
            f"{start_date.isoformat()}/{end_date.isoformat()}"
        )
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": lookback + 50,  # small buffer above requested lookback
            "apiKey": self.api_key,
        }

        try:
            response = self.session.get(url, params=params, timeout=10)
        except requests.RequestException as exc:
            raise ValueError(f"Polygon API request failed: {exc}") from exc

        if response.status_code != 200:
            raise ValueError(f"Polygon API error {response.status_code}: {response.text}")

        try:
            payload: Dict[str, Any] = response.json()
        except ValueError as exc:  # JSONDecodeError
            raise ValueError("Polygon API returned invalid JSON") from exc

        status = payload.get("status")
        if status != "OK":
            message = payload.get("error") or payload.get("message") or f"Unexpected status: {status}"
            raise ValueError(f"Polygon API error: {message}")

        results: List[Dict[str, Any]] = payload.get("results") or []
        if not results:
            raise ValueError(f"No data returned for {symbol}")

        df = pd.DataFrame(results)
        missing_cols = {"t", "o", "h", "l", "c", "v"} - set(df.columns)
        if missing_cols:
            raise ValueError(f"Polygon API response missing expected fields: {sorted(missing_cols)}")

        df = (
            df.loc[:, ["t", "o", "h", "l", "c", "v"]]
            .rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
        )

        df["date"] = (
            pd.to_datetime(df["date"], unit="ms", utc=True)
            .dt.tz_convert(_NY_TZ)
            .dt.tz_localize(None)  # store as naive datetime in local NY time
        )

        df = df.sort_values("date", ascending=True).reset_index(drop=True)
        # Trim to requested lookback (newest last)
        if len(df) > lookback:
            df = df.tail(lookback).reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]


__all__ = ["PolygonProvider"]