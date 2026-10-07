# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Volatility kill switch: halt new openings when VIX or SPY range exceeds thresholds.

Uses publicly available data from yfinance (VIX, SPY). Logic is separate from
the existing risk_off / regime logic so it can be tested independently.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

VIX_SYMBOL = "^VIX"
SPY_SYMBOL = "SPY"

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[misc, assignment]


def fetch_vix(lookback_days: int = 5) -> Optional[float]:
    """Get latest VIX close from yfinance (symbol ^VIX).

    Parameters
    ----------
    lookback_days : int
        Number of days of history to fetch (default 5; need at least 4 for 3-day change).

    Returns
    -------
    Optional[float]
        Latest VIX closing value, or None if fetch fails or no data.
    """
    if yf is None:
        logger.warning("yfinance not installed; cannot fetch VIX")
        return None

    try:
        ticker = yf.Ticker(VIX_SYMBOL)
        hist = ticker.history(period=f"{max(lookback_days, 5)}d", auto_adjust=True)
        if hist.empty or "Close" not in hist.columns:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning("Failed to fetch VIX: %s", e)
        return None


def compute_spy_range(lookback_days: int = 25) -> Tuple[Optional[float], Optional[float]]:
    """Compute SPY current-day range and 20-day average true range (ATR).

    Parameters
    ----------
    lookback_days : int
        Days of history for SPY (default 25 to get 20 full days + buffer).

    Returns
    -------
    Tuple[Optional[float], Optional[float]]
        (current_day_range, atr_20). current_day_range = high - low for the most
        recent trading day. atr_20 = 20-day average of true range.
        Either may be None if data is insufficient or fetch fails.
    """
    if yf is None:
        logger.warning("yfinance not installed; cannot compute SPY range")
        return None, None

    try:
        import pandas as pd
        ticker = yf.Ticker(SPY_SYMBOL)
        hist = ticker.history(period=f"{max(lookback_days, 30)}d", auto_adjust=True)
        if hist.empty or len(hist) < 21:
            return None, None

        df = hist.sort_index(ascending=True)
        # True range: max(high-low, |high-prev_close|, |low-prev_close|)
        high = df["High"]
        low = df["Low"]
        close = df["Close"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        atr_20 = float(tr.rolling(20).mean().iloc[-1]) if len(tr) >= 20 else None

        # Current day range = last row high - low
        last = df.iloc[-1]
        day_range = float(last["High"] - last["Low"]) if pd.notna(last["High"]) and pd.notna(last["Low"]) else None

        return day_range, atr_20
    except Exception as e:
        logger.warning("Failed to compute SPY range: %s", e)
        return None, None


def is_volatility_high(config: Optional[Dict[str, Any]] = None) -> bool:
    """Return True if any volatility condition is exceeded (kill switch triggers).

    Conditions (any one triggers):
    a) VIX close > configured threshold (e.g. 20)
    b) VIX 3-day change > configured percentage (e.g. +20%)
    c) SPY current-day range > range_multiplier × 20-day ATR (e.g. 2×)

    Parameters
    ----------
    config : Optional[Dict[str, Any]]
        Optional overrides. Expected keys: vix_threshold (float), vix_change_pct (float),
        range_multiplier (float). If None, defaults are used (20, 20.0, 2.0).

    Returns
    -------
    bool
        True if volatility is high (kill switch should set regime to Risk-Off).
    """
    cfg = config or {}
    vix_threshold = float(cfg.get("vix_threshold", 20.0))
    vix_change_pct = float(cfg.get("vix_change_pct", 20.0))
    range_multiplier = float(cfg.get("range_multiplier", 2.0))

    if yf is None:
        return False

    # a) VIX level
    vix_now = fetch_vix(lookback_days=5)
    if vix_now is not None and vix_now > vix_threshold:
        logger.info("Volatility kill switch: VIX %.2f > threshold %.2f", vix_now, vix_threshold)
        return True

    # b) VIX 3-day change %
    try:
        ticker = yf.Ticker(VIX_SYMBOL)
        hist = ticker.history(period="10d", auto_adjust=True)
        if not hist.empty and len(hist) >= 4 and "Close" in hist.columns:
            close = hist["Close"]
            vix_today = float(close.iloc[-1])
            vix_3d_ago = float(close.iloc[-4])
            if vix_3d_ago and vix_3d_ago > 0:
                change_pct = 100.0 * (vix_today - vix_3d_ago) / vix_3d_ago
                if change_pct >= vix_change_pct:
                    logger.info(
                        "Volatility kill switch: VIX 3-day change %.1f%% >= %.1f%%",
                        change_pct,
                        vix_change_pct,
                    )
                    return True
    except Exception as e:
        logger.debug("VIX 3-day change check failed: %s", e)

    # c) SPY day range vs 20-day ATR
    day_range, atr_20 = compute_spy_range(lookback_days=25)
    if day_range is not None and atr_20 is not None and atr_20 > 0:
        if day_range > range_multiplier * atr_20:
            logger.info(
                "Volatility kill switch: SPY day range %.4f > %.2f × ATR20 %.4f",
                day_range,
                range_multiplier,
                atr_20,
            )
            return True

    return False
