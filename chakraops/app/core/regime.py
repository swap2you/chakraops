# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Regime detection for risk-on/risk-off market conditions."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


def compute_regime(
    df_daily: pd.DataFrame,
    df_weekly: Optional[pd.DataFrame] = None,
    ema_fast: int = 50,
    ema_slow: int = 200,
    slope_lookback: int = 20,
    require_weekly_confirm: bool = True,
) -> dict:
    """Compute market regime (RISK_ON/RISK_OFF) based on EMA trends and weekly confirmation.

    Parameters
    ----------
    df_daily:
        Daily OHLCV DataFrame with columns: date, open, high, low, close, volume.
        Must be sorted ascending by date (newest last).
    df_weekly:
        Optional weekly OHLCV DataFrame. If None, will be built from daily.
    ema_fast:
        Fast EMA period (default: 50).
    ema_slow:
        Slow EMA period (default: 200).
    slope_lookback:
        Number of periods to use for EMA200 slope calculation (default: 20).
    require_weekly_confirm:
        If True, requires weekly close > weekly EMA200 for RISK_ON (default: True).

    Returns
    -------
    dict
        Contains:
        - regime: "RISK_ON" or "RISK_OFF"
        - confidence: int 0-100
        - details: dict with computed values and boolean flags
    """
    if df_daily.empty:
        raise ValueError("df_daily cannot be empty")

    # Ensure sorted ascending by date (newest last)
    df_daily = df_daily.sort_values("date", ascending=True).reset_index(drop=True)

    # Compute EMAs on daily data
    df_daily = df_daily.copy()
    df_daily["ema_fast"] = df_daily["close"].ewm(span=ema_fast, adjust=False).mean()
    df_daily["ema_slow"] = df_daily["close"].ewm(span=ema_slow, adjust=False).mean()

    # Get latest values
    latest = df_daily.iloc[-1]
    close = latest["close"]
    ema_fast_val = latest["ema_fast"]
    ema_slow_val = latest["ema_slow"]

    # Compute EMA200 slope using linear regression on last slope_lookback points
    if len(df_daily) < slope_lookback:
        slope_lookback_actual = len(df_daily)
    else:
        slope_lookback_actual = slope_lookback

    ema_slow_recent = df_daily["ema_slow"].tail(slope_lookback_actual).values
    # Use indices as x values for regression
    x = np.arange(len(ema_slow_recent))
    
    # Simple linear regression: slope = covariance / variance
    x_mean = x.mean()
    y_mean = ema_slow_recent.mean()
    numerator = ((x - x_mean) * (ema_slow_recent - y_mean)).sum()
    denominator = ((x - x_mean) ** 2).sum()
    
    if denominator == 0:
        ema_slope = 0.0
    else:
        ema_slope = numerator / denominator

    # Daily conditions
    daily_conditions = {
        "close_above_ema200": close > ema_slow_val,
        "ema50_above_ema200": ema_fast_val > ema_slow_val,
        "ema200_slope_positive": ema_slope >= 0,
    }

    # Check if all daily conditions are met
    daily_risk_on = all(daily_conditions.values())

    # Weekly confirmation
    weekly_confirm = True
    weekly_conditions = {}
    
    if require_weekly_confirm:
        if df_weekly is None:
            # Build weekly from daily
            df_weekly = build_weekly_from_daily(df_daily)
        
        if df_weekly.empty:
            weekly_confirm = False
            weekly_conditions = {"error": "Weekly data is empty"}
        else:
            # Ensure sorted ascending
            df_weekly = df_weekly.sort_values("date", ascending=True).reset_index(drop=True)
            
            # Compute weekly EMA200
            df_weekly = df_weekly.copy()
            df_weekly["ema_slow"] = df_weekly["close"].ewm(span=ema_slow, adjust=False).mean()
            
            latest_weekly = df_weekly.iloc[-1]
            weekly_close = latest_weekly["close"]
            weekly_ema200 = latest_weekly["ema_slow"]
            
            weekly_confirm = weekly_close > weekly_ema200
            weekly_conditions = {
                "weekly_close_above_ema200": weekly_confirm,
                "weekly_close": float(weekly_close),
                "weekly_ema200": float(weekly_ema200),
            }

    # Determine regime
    risk_on = daily_risk_on and weekly_confirm

    # Calculate confidence (0-100)
    # Count how many conditions are met
    conditions_met = sum(daily_conditions.values()) + (1 if weekly_confirm else 0)
    total_conditions = len(daily_conditions) + (1 if require_weekly_confirm else 0)
    confidence = int((conditions_met / total_conditions) * 100) if total_conditions > 0 else 0

    regime = "RISK_ON" if risk_on else "RISK_OFF"

    details = {
        "daily": {
            "close": float(close),
            "ema_fast": float(ema_fast_val),
            "ema_slow": float(ema_slow_val),
            "ema_slope": float(ema_slope),
            **daily_conditions,
        },
        "weekly": weekly_conditions if require_weekly_confirm else None,
        "daily_risk_on": daily_risk_on,
        "weekly_confirm": weekly_confirm if require_weekly_confirm else None,
    }

    return {
        "regime": regime,
        "confidence": confidence,
        "details": details,
    }


def build_weekly_from_daily(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Build weekly OHLCV candles from daily data.

    Parameters
    ----------
    df_daily:
        Daily OHLCV DataFrame with columns: date, open, high, low, close, volume.

    Returns
    -------
    pd.DataFrame
        Weekly OHLCV DataFrame with same columns, sorted ascending by date.
    """
    if df_daily.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = df_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    # Resample to weekly (Monday as week start)
    weekly = df.resample("W").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    weekly = weekly.reset_index()
    weekly = weekly.rename(columns={"date": "date"})

    # Remove any rows with NaN (incomplete weeks)
    weekly = weekly.dropna().reset_index(drop=True)

    return weekly


def build_monthly_from_daily(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Build monthly OHLCV bars from daily data. open=first, high=max, low=min, close=last, volume=sum."""
    if df_daily.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    df = df_daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    monthly = df.resample("M").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    monthly = monthly.reset_index()
    monthly = monthly.rename(columns={"date": "date"})
    monthly = monthly.dropna().reset_index(drop=True)
    return monthly


__all__ = ["compute_regime", "build_weekly_from_daily", "build_monthly_from_daily"]
