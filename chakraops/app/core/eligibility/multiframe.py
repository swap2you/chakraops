# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4.3: Multi-timeframe regime. Daily + weekly; weekly is primary."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.eligibility import candles as candles_mod
from app.core.eligibility.eligibility_engine import classify_regime
from app.core.eligibility.indicators import ema
from app.core.eligibility.config import EMA_FAST, EMA_MID, EMA_SLOW

WEEKLY_EMA_PERIOD = 20
DEFAULT_LOOKBACK_DAYS = 400


def _resample_daily_to_weekly(daily_candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group daily candles into weekly bars (Mon–Fri). Each week: O=first open, H=max high, L=min low, C=last close."""
    if not daily_candles:
        return []
    from datetime import datetime
    # Group by (year, ISO week)
    weeks: Dict[tuple, List[Dict[str, Any]]] = {}
    for c in daily_candles:
        ts = c.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.strptime(str(ts)[:10], "%Y-%m-%d")
            y, w, _ = dt.isocalendar()
            key = (y, w)
        except (ValueError, TypeError):
            continue
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(c)
    out: List[Dict[str, Any]] = []
    for key in sorted(weeks.keys()):
        bars = weeks[key]
        if not bars:
            continue
        opens = [b.get("open") for b in bars if b.get("open") is not None]
        highs = [b.get("high") for b in bars if b.get("high") is not None]
        lows = [b.get("low") for b in bars if b.get("low") is not None]
        closes = [b.get("close") for b in bars if b.get("close") is not None]
        if not closes:
            continue
        first_ts = bars[0].get("ts") or bars[-1].get("ts")
        out.append({
            "ts": first_ts,
            "open": opens[0] if opens else None,
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "close": closes[-1] if closes else None,
            "volume": sum(b.get("volume") or 0 for b in bars),
        })
    return out


def _resample_daily_to_monthly(daily_candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group daily candles into monthly bars. O=first open, H=max high, L=min low, C=last close, V=sum."""
    if not daily_candles:
        return []
    months: Dict[tuple, List[Dict[str, Any]]] = {}
    for c in daily_candles:
        ts = c.get("ts")
        if not ts:
            continue
        try:
            dt = datetime.strptime(str(ts)[:10], "%Y-%m-%d")
            key = (dt.year, dt.month)
        except (ValueError, TypeError):
            continue
        if key not in months:
            months[key] = []
        months[key].append(c)
    out: List[Dict[str, Any]] = []
    for key in sorted(months.keys()):
        bars = months[key]
        if not bars:
            continue
        opens = [b.get("open") for b in bars if b.get("open") is not None]
        highs = [b.get("high") for b in bars if b.get("high") is not None]
        lows = [b.get("low") for b in bars if b.get("low") is not None]
        closes = [b.get("close") for b in bars if b.get("close") is not None]
        if not closes:
            continue
        first_ts = bars[0].get("ts") or bars[-1].get("ts")
        out.append({
            "ts": first_ts,
            "open": opens[0] if opens else None,
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "close": closes[-1] if closes else None,
            "volume": sum(b.get("volume") or 0 for b in bars),
        })
    return out


def get_daily_regime(symbol: str, lookback: int = 255) -> str:
    """Compute daily timeframe regime (UP, DOWN, SIDEWAYS) from daily candles."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return "SIDEWAYS"
    cands = candles_mod.get_candles(sym, "daily", lookback)
    if not cands or len(cands) < EMA_SLOW:
        return "SIDEWAYS"
    closes = [float(c["close"]) for c in cands if c.get("close") is not None]
    if len(closes) < EMA_SLOW:
        return "SIDEWAYS"
    from app.core.eligibility.indicators import ema_slope
    ema20 = ema(closes, EMA_FAST)
    ema50 = ema(closes, EMA_MID)
    ema200 = ema(closes, EMA_SLOW)
    ema50_slope = ema_slope(closes, EMA_MID, 5)
    return classify_regime(closes, ema20, ema50, ema200, ema50_slope)


def get_weekly_regime(symbol: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> str:
    """Compute weekly regime from daily candles resampled to weekly. Uses EMA(20) on weekly closes."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return "SIDEWAYS"
    cands = candles_mod.get_candles(sym, "daily", lookback_days)
    if not cands:
        return "SIDEWAYS"
    weekly = _resample_daily_to_weekly(cands)
    if len(weekly) < WEEKLY_EMA_PERIOD:
        return "SIDEWAYS"
    w_closes = [float(w["close"]) for w in weekly if w.get("close") is not None]
    if len(w_closes) < WEEKLY_EMA_PERIOD:
        return "SIDEWAYS"
    ema20_w = ema(w_closes, WEEKLY_EMA_PERIOD)
    if ema20_w is None:
        return "SIDEWAYS"
    last_close = w_closes[-1]
    if last_close > ema20_w:
        return "UP"
    if last_close < ema20_w:
        return "DOWN"
    return "SIDEWAYS"


def daily_weekly_aligned(daily_regime: str, weekly_regime: str) -> bool:
    """True if daily and weekly regimes agree (no conflict)."""
    return daily_regime == weekly_regime
