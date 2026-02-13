# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: RSI (Wilder), EMA, ATR. Deterministic, unit-testable."""

from __future__ import annotations

from typing import List, Optional


def rsi_wilder(close: List[float], period: int = 14) -> Optional[float]:
    """
    RSI using Wilder smoothing: RSI = 100 - 100/(1+RS).
    Returns None if not enough data.
    """
    if not close or len(close) < period + 1 or period < 1:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(close)):
        ch = close[i] - close[i - 1]
        gains.append(ch if ch > 0 else 0.0)
        losses.append(-ch if ch < 0 else 0.0)
    if len(gains) < period:
        return None
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def ema(close: List[float], period: int) -> Optional[float]:
    """EMA(period) of close; last value. Returns None if len(close) < period."""
    if not close or len(close) < period or period < 1:
        return None
    k = 2.0 / (period + 1)
    ema_val = sum(close[:period]) / period
    for i in range(period, len(close)):
        ema_val = close[i] * k + ema_val * (1 - k)
    return ema_val


def ema_series(close: List[float], period: int) -> List[Optional[float]]:
    """EMA for each index (None for indices < period-1)."""
    if not close or period < 1:
        return []
    k = 2.0 / (period + 1)
    out: List[Optional[float]] = [None] * (period - 1)
    ema_val = sum(close[:period]) / period
    out.append(ema_val)
    for i in range(period, len(close)):
        ema_val = close[i] * k + ema_val * (1 - k)
        out.append(ema_val)
    return out


def atr(high: List[float], low: List[float], close: List[float], period: int = 14) -> Optional[float]:
    """ATR(period): Wilder smoothing of true range. Returns last ATR."""
    n = len(close)
    if n < period + 1 or len(high) < n or len(low) < n or period < 1:
        return None
    tr_list: List[float] = []
    for i in range(1, n):
        hl = high[i] - low[i]
        h_pc = abs(high[i] - close[i - 1])
        l_pc = abs(low[i] - close[i - 1])
        tr_list.append(max(hl, h_pc, l_pc))
    if len(tr_list) < period:
        return None
    atr_val = sum(tr_list[:period]) / period
    for i in range(period, len(tr_list)):
        atr_val = (atr_val * (period - 1) + tr_list[i]) / period
    return atr_val


def atr_pct(high: List[float], low: List[float], close: List[float], period: int = 14) -> Optional[float]:
    """ATR(period) / close[-1] as decimal."""
    a = atr(high, low, close, period)
    if a is None or not close:
        return None
    last = close[-1]
    if last is None or last == 0:
        return None
    return a / last


def ema_slope(close: List[float], period: int, bars: int = 5) -> Optional[float]:
    """Slope of EMA over last bars: (ema[-1] - ema[-bars]) / bars."""
    series = ema_series(close, period)
    if not series or len(series) < bars:
        return None
    valid = [x for x in series[-bars:] if x is not None]
    if len(valid) < 2:
        return None
    return (valid[-1] - valid[0]) / len(valid)
