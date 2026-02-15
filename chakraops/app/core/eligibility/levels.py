# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Pivot points (prior day) and swing high/low from candles."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Sanity bounds: swing must be within ±50% of last close (else recompute with shorter lookback)
SWING_LOW_MIN_RATIO = 0.5
SWING_HIGH_MAX_RATIO = 1.5
SWING_SANITY_LOOKBACK = 50


def pivot_classic(high: float, low: float, close: float) -> Dict[str, float]:
    """Classic pivot from prior bar: P = (H+L+C)/3, R1 = 2*P - L, S1 = 2*P - H."""
    p = (high + low + close) / 3.0
    return {
        "P": p,
        "R1": 2.0 * p - low,
        "S1": 2.0 * p - high,
    }


def pivots_from_candles(candles: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Pivot from prior day (second-to-last candle)."""
    if not candles or len(candles) < 2:
        return None
    prev = candles[-2]
    h = prev.get("high")
    l_ = prev.get("low")
    c = prev.get("close")
    if h is None or l_ is None or c is None:
        return None
    return pivot_classic(float(h), float(l_), float(c))


def _swing_high_impl(candles: List[Dict[str, Any]], lookback: int, skip_sanity: bool) -> Optional[float]:
    if not candles or lookback <= 0:
        return None
    window = candles[-lookback:]
    highs = [c.get("high") for c in window if c.get("high") is not None]
    val = max(highs) if highs else None
    if val is not None and not skip_sanity and len(candles) > 0:
        last_close = candles[-1].get("close")
        if last_close is not None and float(last_close) > 0:
            if val > float(last_close) * SWING_HIGH_MAX_RATIO:
                logger.debug(
                    "[levels] swing_high %.2f > close*%.1f (%.2f); recomputing with last %d candles",
                    val, SWING_HIGH_MAX_RATIO, float(last_close), SWING_SANITY_LOOKBACK,
                )
                return _swing_high_impl(
                    candles, min(SWING_SANITY_LOOKBACK, len(candles)), skip_sanity=True
                )
    return val


def swing_high(candles: List[Dict[str, Any]], lookback: int = 30) -> Optional[float]:
    """Max high over last lookback candles. If result > close*1.5, recompute with last 50 only."""
    return _swing_high_impl(candles, lookback, skip_sanity=False)


def _swing_low_impl(candles: List[Dict[str, Any]], lookback: int, skip_sanity: bool) -> Optional[float]:
    if not candles or lookback <= 0:
        return None
    window = candles[-lookback:]
    lows = [c.get("low") for c in window if c.get("low") is not None]
    val = min(lows) if lows else None
    if val is not None and not skip_sanity and len(candles) > 0:
        last_close = candles[-1].get("close")
        if last_close is not None and float(last_close) > 0:
            if val < float(last_close) * SWING_LOW_MIN_RATIO:
                logger.debug(
                    "[levels] swing_low %.2f < close*%.1f (%.2f); recomputing with last %d candles",
                    val, SWING_LOW_MIN_RATIO, float(last_close), SWING_SANITY_LOOKBACK,
                )
                return _swing_low_impl(
                    candles, min(SWING_SANITY_LOOKBACK, len(candles)), skip_sanity=True
                )
    return val


def swing_low(candles: List[Dict[str, Any]], lookback: int = 30) -> Optional[float]:
    """Min low over last lookback candles. If result < close*0.5, recompute with last 50 only."""
    return _swing_low_impl(candles, lookback, skip_sanity=False)


def distance_to_support_pct(close: float, s1: Optional[float], swing_low_val: Optional[float]) -> Optional[float]:
    """Min distance to S1 and swing_low as positive pct (e.g. 0.02 = 2% below close)."""
    if close <= 0:
        return None
    dists: List[float] = []
    if s1 is not None:
        dists.append(abs(close - s1) / close)
    if swing_low_val is not None:
        dists.append(abs(close - swing_low_val) / close)
    return min(dists) if dists else None


def distance_to_resistance_pct(close: float, r1: Optional[float], swing_high_val: Optional[float]) -> Optional[float]:
    """Min distance to R1 and swing_high as positive pct."""
    if close <= 0:
        return None
    dists: List[float] = []
    if r1 is not None:
        dists.append(abs(close - r1) / close)
    if swing_high_val is not None:
        dists.append(abs(close - swing_high_val) / close)
    return min(dists) if dists else None
