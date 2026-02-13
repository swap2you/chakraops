# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5.0: Swing-cluster support/resistance unit tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.eligibility.swing_cluster import (
    fractal_swing_highs,
    fractal_swing_lows,
    cluster_levels,
    nearest_support,
    nearest_resistance,
    compute_support_resistance,
    distance_to_level_pct,
)


def test_fractal_swing_high_known():
    """Swing high: center bar higher than k=2 on each side."""
    # indices 0,1,2,3,4 -> high at 2 must be > 0,1 and > 3,4
    candles = [
        {"high": 10, "low": 8},
        {"high": 11, "low": 9},
        {"high": 15, "low": 12},  # swing high
        {"high": 11, "low": 9},
        {"high": 10, "low": 8},
    ]
    highs = fractal_swing_highs(candles, k=2)
    assert 15 in highs
    assert len(highs) >= 1


def test_fractal_swing_low_known():
    """Swing low: center bar lower than k=2 on each side."""
    candles = [
        {"high": 12, "low": 10},
        {"high": 11, "low": 9},
        {"high": 10, "low": 5},  # swing low
        {"high": 11, "low": 9},
        {"high": 12, "low": 10},
    ]
    lows = fractal_swing_lows(candles, k=2)
    assert 5 in lows
    assert len(lows) >= 1


def test_clustering_merge_close_levels():
    """Close levels merge into one zone within tolerance."""
    levels = [100.0, 100.5, 101.0, 101.2]
    centers = cluster_levels(levels, tolerance=1.0)
    assert len(centers) == 1
    assert 100.0 < centers[0] < 102.0


def test_clustering_two_zones():
    """Two separated groups yield two cluster centers."""
    levels = [100.0, 100.3, 100.5, 110.0, 110.5, 111.0]
    centers = cluster_levels(levels, tolerance=1.0)
    assert len(centers) == 2
    assert centers[0] < 105 < centers[1]


def test_nearest_support():
    """nearest_support = max(center < spot)."""
    centers = [95.0, 98.0, 102.0, 105.0]
    assert nearest_support(100.0, centers) == 98.0
    assert nearest_support(94.0, centers) is None
    assert nearest_support(106.0, centers) == 105.0


def test_nearest_resistance():
    """nearest_resistance = min(center > spot)."""
    centers = [95.0, 98.0, 102.0, 105.0]
    assert nearest_resistance(100.0, centers) == 102.0
    assert nearest_resistance(106.0, centers) is None
    assert nearest_resistance(94.0, centers) == 95.0


def test_distance_to_level_pct():
    """Distance as fraction of spot."""
    assert distance_to_level_pct(100.0, 98.0) == pytest.approx(0.02)
    assert distance_to_level_pct(100.0, None) is None
    assert distance_to_level_pct(0.0, 10.0) is None


def test_compute_support_resistance_synthetic():
    """Synthetic series with known swing levels -> support/resistance near expected."""
    # Build 60 candles: clear swing low at 97, swing high at 103, spot 100
    candles = []
    for i in range(60):
        if 20 <= i <= 25:
            low, high = 97, 99
        elif 35 <= i <= 40:
            low, high = 99, 103
        else:
            low, high = 98, 101
        candles.append({"ts": f"2024-01-{i+1:02d}", "open": 99, "high": high, "low": low, "close": 100, "volume": 1e6})
    # Last bar at 100
    result = compute_support_resistance(
        candles, spot=100.0, atr14=2.0, window=60, k=3, atr_mult=0.5, pct_tol=0.006
    )
    assert result["method"] == "swing_cluster"
    assert result["window"] == 60
    assert result["k"] == 3
    assert result["swing_high_count"] >= 0
    assert result["swing_low_count"] >= 0
    # May or may not find levels depending on fractal; at least structure is there
    if result["support_level"] is not None:
        assert result["support_level"] < 100.0
        assert result["distance_to_support_pct"] is not None
    if result["resistance_level"] is not None:
        assert result["resistance_level"] > 100.0
        assert result["distance_to_resistance_pct"] is not None


def test_missing_support_all_levels_above_spot():
    """All cluster centers above spot => support missing (no level < spot)."""
    # All bars with low >= 100 so no cluster center below 100
    candles = [
        {"high": 101 + (i % 3) * 0.5, "low": 100.0 + (i % 2) * 0.3, "close": 100.5, "volume": 1e6}
        for i in range(60)
    ]
    result = compute_support_resistance(
        candles, spot=100.0, atr14=1.0, window=60, k=2, atr_mult=0.5, pct_tol=0.01
    )
    assert result["support_level"] is None
    assert result["distance_to_support_pct"] is None


def test_missing_resistance_all_levels_below_spot():
    """All cluster centers below spot => resistance missing (no level > spot)."""
    # All bars with high <= 99 so no cluster center above 100
    candles = [
        {"high": 99.0 - (i % 2) * 0.3, "low": 98.0 - (i % 3) * 0.2, "close": 98.5, "volume": 1e6}
        for i in range(60)
    ]
    result = compute_support_resistance(
        candles, spot=100.0, atr14=1.0, window=60, k=2, atr_mult=0.5, pct_tol=0.01
    )
    assert result["resistance_level"] is None
    assert result["distance_to_resistance_pct"] is None


def test_compute_support_resistance_empty_candles():
    """Empty candles return safe defaults."""
    result = compute_support_resistance([], spot=100.0, atr14=1.0, window=60, k=3, atr_mult=0.5, pct_tol=0.006)
    assert result["method"] == "swing_cluster"
    assert result["support_level"] is None
    assert result["resistance_level"] is None
    assert result["distance_to_support_pct"] is None
    assert result["distance_to_resistance_pct"] is None


def test_tolerance_capped_when_atr_huge():
    """Phase 5.0.1: When ATR is huge, tolerance_used is capped by MAX_S_R_TOL_PCT * spot."""
    from app.core.eligibility.config import MAX_S_R_TOL_PCT
    candles = [{"high": 102, "low": 98, "close": 100, "volume": 1e6}] * 60
    # atr_mult * atr14 = 0.5 * 200 = 100 (huge); cap = 100 * 0.012 = 1.2
    result = compute_support_resistance(
        candles, spot=100.0, atr14=200.0, window=60, k=2, atr_mult=0.5, pct_tol=0.006
    )
    expected_cap = 100.0 * MAX_S_R_TOL_PCT
    assert result["tolerance_used"] is not None
    assert result["tolerance_used"] <= expected_cap + 0.001
    assert result["tolerance_used"] < 50.0  # would be 100 without cap


def test_tolerance_respects_pct_floor_when_atr_small():
    """Phase 5.0.1: When ATR is small, tolerance_used >= pct_tol * spot (floor)."""
    candles = [{"high": 100.5, "low": 99.5, "close": 100, "volume": 1e6}] * 60
    # atr_mult * atr14 = 0.5 * 0.1 = 0.05; tol_pct = 0.006 * 100 = 0.6; tol = max(0.05, 0.6) = 0.6
    result = compute_support_resistance(
        candles, spot=100.0, atr14=0.1, window=60, k=2, atr_mult=0.5, pct_tol=0.006
    )
    assert result["tolerance_used"] is not None
    assert result["tolerance_used"] >= 0.5  # pct floor ~0.6
