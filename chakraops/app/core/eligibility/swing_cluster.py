# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5.0: Support/Resistance from fractal swing points + ATR-based clustering."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.eligibility.config import (
    S_R_ATR_MULT,
    S_R_PCT_TOL,
    SWING_CLUSTER_WINDOW,
    SWING_FRACTAL_K,
)


def fractal_swing_highs(candles: List[Dict[str, Any]], k: int = 3) -> List[float]:
    """
    Swing highs: high[i] is a swing high iff
    high[i] > all highs in [i-k..i-1] and > all highs in [i+1..i+k].
    Uses only the candles given (caller should pass last WINDOW candles).
    """
    if not candles or k < 1:
        return []
    highs: List[float] = []
    for i, c in enumerate(candles):
        h = c.get("high")
        if h is None:
            continue
        try:
            val = float(h)
        except (TypeError, ValueError):
            continue
        left_ok = all(
            val > (float(candles[j].get("high") or 0))
            for j in range(max(0, i - k), i)
            if candles[j].get("high") is not None
        )
        right_ok = all(
            val > (float(candles[j].get("high") or 0))
            for j in range(i + 1, min(len(candles), i + k + 1))
            if candles[j].get("high") is not None
        )
        if left_ok and right_ok:
            highs.append(val)
    return highs


def fractal_swing_lows(candles: List[Dict[str, Any]], k: int = 3) -> List[float]:
    """
    Swing lows: low[i] is a swing low iff
    low[i] < all lows in [i-k..i-1] and < all lows in [i+1..i+k].
    """
    if not candles or k < 1:
        return []
    lows: List[float] = []
    for i, c in enumerate(candles):
        l_ = c.get("low")
        if l_ is None:
            continue
        try:
            val = float(l_)
        except (TypeError, ValueError):
            continue
        left_ok = all(
            val < (float(candles[j].get("low") or 1e99))
            for j in range(max(0, i - k), i)
            if candles[j].get("low") is not None
        )
        right_ok = all(
            val < (float(candles[j].get("low") or 1e99))
            for j in range(i + 1, min(len(candles), i + k + 1))
            if candles[j].get("low") is not None
        )
        if left_ok and right_ok:
            lows.append(val)
    return lows


def _median(x: List[float]) -> float:
    if not x:
        return 0.0
    s = sorted(x)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def cluster_levels(levels: List[float], tolerance: float) -> List[float]:
    """
    Sort levels and merge into clusters: add to cluster if abs(level - cluster_median) <= tolerance.
    Cluster center = median of cluster members. Returns list of cluster centers (sorted).
    """
    if not levels or tolerance <= 0:
        return []
    sorted_vals = sorted(levels)
    clusters: List[List[float]] = []
    current: List[float] = [sorted_vals[0]]
    for v in sorted_vals[1:]:
        center = _median(current)
        if abs(v - center) <= tolerance:
            current.append(v)
        else:
            clusters.append(current)
            current = [v]
    if current:
        clusters.append(current)
    return sorted(_median(c) for c in clusters)


def nearest_support(spot: float, cluster_centers: List[float]) -> Optional[float]:
    """Max(center < spot); None if no center below spot."""
    below = [c for c in cluster_centers if c < spot]
    return max(below) if below else None


def nearest_resistance(spot: float, cluster_centers: List[float]) -> Optional[float]:
    """Min(center > spot); None if no center above spot."""
    above = [c for c in cluster_centers if c > spot]
    return min(above) if above else None


def distance_to_level_pct(spot: float, level: Optional[float]) -> Optional[float]:
    """Absolute distance as fraction of spot (e.g. 0.02 = 2%)."""
    if spot <= 0 or level is None:
        return None
    return abs(spot - level) / spot


def compute_support_resistance(
    candles: List[Dict[str, Any]],
    spot: float,
    atr14: Optional[float],
    window: int,
    k: int,
    atr_mult: float,
    pct_tol: float,
) -> Dict[str, Any]:
    """
    Phase 5.0: Fractal swing points in last `window` candles, cluster with ATR-based tolerance,
    then nearest support/resistance below/above spot. Returns dict for eligibility trace.
    """
    out: Dict[str, Any] = {
        "method": "swing_cluster",
        "window": window,
        "k": k,
        "tolerance_used": None,
        "swing_high_count": 0,
        "swing_low_count": 0,
        "cluster_count": 0,
        "support_level": None,
        "resistance_level": None,
        "distance_to_support_pct": None,
        "distance_to_resistance_pct": None,
    }
    if not candles or spot <= 0:
        return out
    use = candles[-window:] if len(candles) >= window else candles
    if len(use) < 2 * k + 1:
        return out

    swing_highs = fractal_swing_highs(use, k)
    swing_lows = fractal_swing_lows(use, k)
    out["swing_high_count"] = len(swing_highs)
    out["swing_low_count"] = len(swing_lows)

    tol_atr = (atr_mult * atr14) if atr14 is not None and atr14 > 0 else 0.0
    tol_pct = pct_tol * spot
    tolerance = max(tol_atr, tol_pct)
    if tolerance <= 0:
        tolerance = tol_pct if tol_pct > 0 else (spot * 0.006)
    out["tolerance_used"] = round(tolerance, 6)

    all_levels = swing_highs + swing_lows
    centers = cluster_levels(all_levels, tolerance)
    out["cluster_count"] = len(centers)

    sup = nearest_support(spot, centers)
    res = nearest_resistance(spot, centers)
    out["support_level"] = round(sup, 4) if sup is not None else None
    out["resistance_level"] = round(res, 4) if res is not None else None
    out["distance_to_support_pct"] = round(distance_to_level_pct(spot, sup), 6) if sup is not None else None
    out["distance_to_resistance_pct"] = round(distance_to_level_pct(spot, res), 6) if res is not None else None
    return out
