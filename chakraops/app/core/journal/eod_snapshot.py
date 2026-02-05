# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""EOD snapshot for exit rules: close, EMA50, EMA20, ATR14, RSI. Fetched from daily bars."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class EODSnapshot:
    """End-of-day snapshot for one symbol. All fields optional when data unavailable."""
    close: Optional[float] = None
    ema50: Optional[float] = None
    ema20: Optional[float] = None
    atr14: Optional[float] = None
    rsi: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "close": self.close,
            "ema50": self.ema50,
            "ema20": self.ema20,
            "atr14": self.atr14,
            "rsi": self.rsi,
        }


def _compute_atr14(df: "Any") -> Optional[float]:
    """Compute 14-period ATR from OHLC DataFrame (last row). Requires 'high', 'low', 'close'."""
    import pandas as pd
    if df is None or df.empty or len(df) < 15:
        return None
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().iloc[-1]
    return float(atr) if pd.notna(atr) else None


def _compute_rsi14(df: "Any") -> Optional[float]:
    """Compute 14-period RSI from close series (last value)."""
    import pandas as pd
    if df is None or df.empty or len(df) < 15:
        return None
    close = df["close"]
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(14).mean().iloc[-1]
    avg_loss = loss.rolling(14).mean().iloc[-1]
    if avg_loss == 0 or pd.isna(avg_loss):
        return 100.0 if (avg_gain and float(avg_gain) > 0) else None
    rs = float(avg_gain) / float(avg_loss)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def get_eod_snapshot(
    symbol: str,
    daily_provider: Optional[Callable[[str, int], Any]] = None,
) -> EODSnapshot:
    """
    Build EOD snapshot for symbol: close, EMA50, EMA20, ATR14, RSI.
    daily_provider(symbol, lookback) -> DataFrame with columns date, open, high, low, close, volume.
    Default: use YFinanceMarketDataAdapter.get_daily if available.
    """
    lookback = 120  # enough for EMA50 + ATR/RSI 14
    snapshot = EODSnapshot()
    df = None

    try:
        if daily_provider is not None:
            df = daily_provider(symbol, lookback)
        else:
            from app.core.market_data.yfinance_adapter import YFinanceMarketDataAdapter
            adapter = YFinanceMarketDataAdapter()
            df = adapter.get_daily(symbol, lookback=lookback)
    except Exception as e:
        logger.debug("[EOD_SNAPSHOT] %s: fetch failed: %s", symbol, e)
        return snapshot

    if df is None or df.empty:
        return snapshot

    import pandas as pd
    # Latest close
    if "close" in df.columns:
        last_close = df["close"].iloc[-1]
        if pd.notna(last_close):
            snapshot.close = float(last_close)

    if len(df) < 50:
        return snapshot

    # EMA50, EMA20
    close_series = df["close"]
    snapshot.ema50 = float(close_series.ewm(span=50, adjust=False).mean().iloc[-1])
    if len(df) >= 20:
        snapshot.ema20 = float(close_series.ewm(span=20, adjust=False).mean().iloc[-1])

    snapshot.atr14 = _compute_atr14(df)
    snapshot.rsi = _compute_rsi14(df)
    return snapshot
