# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CSP (Cash-Secured Put) candidate finder based on market regime."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def find_csp_candidates(symbol_to_df: Dict[str, pd.DataFrame], regime: str) -> List[Dict[str, Any]]:
    """Find CSP candidates based on regime and technical filters.

    Parameters
    ----------
    symbol_to_df:
        Dictionary mapping symbol to daily OHLCV DataFrame with columns:
        date, open, high, low, close, volume. Must be sorted ascending by date.
    regime:
        Market regime: "RISK_ON" or "RISK_OFF".

    Returns
    -------
    list[dict]
        List of candidate dictionaries, each containing:
        - symbol: str
        - score: int (0-100)
        - reasons: list[str]
        - key_levels: dict with ema50, ema200, close
    """
    if regime != "RISK_ON":
        return []

    candidates = []

    for symbol, df in symbol_to_df.items():
        if df.empty:
            continue

        # Ensure sorted ascending
        df = df.sort_values("date", ascending=True).reset_index(drop=True)

        # Calculate EMAs
        df = df.copy()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        # Calculate ATR (14-period)
        df["high_low"] = df["high"] - df["low"]
        df["high_close"] = abs(df["high"] - df["close"].shift(1))
        df["low_close"] = abs(df["low"] - df["close"].shift(1))
        df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)
        df["atr"] = df["tr"].rolling(window=14, min_periods=1).mean()

        # Calculate RSI(14)
        df["rsi"] = calculate_rsi(df["close"], period=14)

        # Get latest values
        latest = df.iloc[-1]
        close = latest["close"]
        ema50 = latest["ema50"]
        ema200 = latest["ema200"]
        atr = latest["atr"]
        rsi = latest["rsi"]

        # Apply filters
        reasons = []
        score_points = 0

        # 1. Uptrend filter: close > EMA200
        uptrend = close > ema200
        if uptrend:
            reasons.append("Uptrend: close > EMA200")
            score_points += 40
        else:
            continue  # Must pass uptrend filter

        # 2. Pullback filter: close near EMA50
        # Option 1: Within 1.0 ATR
        distance_atr = abs(close - ema50) / atr if atr > 0 else float("inf")
        # Option 2: Within 2% of EMA50
        distance_pct = abs(close - ema50) / ema50 * 100 if ema50 > 0 else float("inf")

        near_ema50 = distance_atr <= 1.0 or distance_pct <= 2.0

        if near_ema50:
            reasons.append(f"Pullback: close near EMA50 (ATR: {distance_atr:.2f}, %: {distance_pct:.2f})")
            score_points += 30
        else:
            continue  # Must pass pullback filter

        # 3. RSI filter: RSI < 55
        if pd.notna(rsi) and rsi < 55:
            reasons.append(f"RSI: {rsi:.1f} < 55 (oversold)")
            score_points += 30
        else:
            # Not required, but nice to have
            if pd.notna(rsi):
                reasons.append(f"RSI: {rsi:.1f} (not oversold)")

        # Additional score adjustments
        if pd.notna(rsi) and rsi < 45:
            score_points += 10  # Bonus for very oversold

        # Ensure score is within 0-100
        score = min(100, max(0, score_points))

        candidates.append({
            "symbol": symbol,
            "score": score,
            "reasons": reasons,
            "key_levels": {
                "close": float(close),
                "ema50": float(ema50),
                "ema200": float(ema200),
                "atr": float(atr) if pd.notna(atr) else None,
                "rsi": float(rsi) if pd.notna(rsi) else None,
            },
        })

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Relative Strength Index (RSI).

    Parameters
    ----------
    close:
        Series of closing prices.
    period:
        Period for RSI calculation (default: 14).

    Returns
    -------
    pd.Series
        RSI values (0-100).
    """
    delta = close.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Calculate average gain and loss using exponential moving average
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


__all__ = ["find_csp_candidates", "calculate_rsi"]
