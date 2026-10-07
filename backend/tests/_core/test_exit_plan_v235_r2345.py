# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4.5: build_exit_plan_v235 — targets validity, next resistance when nearest below spot, ATR fallback, monotonic T1<T2<T3."""

from __future__ import annotations

import pytest

from app.core.lifecycle.exit_planner import build_exit_plan_v235


def test_targets_monotonic_increasing_csp():
    """CSP: T1 < T2 < T3 when using valid resistance above spot."""
    spot = 190.0
    atr = 2.0
    # One resistance well above spot (e.g. 200) -> T1 midpoint, T2=200, T3 extension
    resistances_by_tf = {
        "daily": [{"level": 200.0, "distance_pct": 0.052}],
        "weekly": [],
        "monthly": [],
    }
    supports_by_tf = {
        "daily": [{"level": 185.0, "distance_pct": 0.026}],
        "weekly": [],
        "monthly": [],
    }
    out = build_exit_plan_v235(
        spot, "CSP", atr, resistances_by_tf, supports_by_tf,
        min_distance_pct=0.002, eps_pct=0.001,
    )
    sp = out["structure_plan"]
    t1, t2, t3 = sp["T1"], sp["T2"], sp["T3"]
    assert t1 is not None and t2 is not None and t3 is not None
    assert t1 < t2 < t3
    assert out["target_basis"] == "SR_LEVEL"
    assert out["level_source_timeframe"] == "daily"


def test_targets_use_next_resistance_when_nearest_below_spot():
    """When nearest resistance is at or below spot (within epsilon), use next higher resistance."""
    spot = 193.69
    atr = 1.5
    # First resistance ~193.65 (below spot), second at 198
    resistances_by_tf = {
        "daily": [
            {"level": 193.65, "distance_pct": 0.0002},  # too close / effectively at spot
            {"level": 198.0, "distance_pct": 0.022},
        ],
        "weekly": [],
        "monthly": [],
    }
    supports_by_tf = {"daily": [{"level": 188.0, "distance_pct": 0.029}], "weekly": [], "monthly": []}
    out = build_exit_plan_v235(
        spot, "CSP", atr, resistances_by_tf, supports_by_tf,
        min_distance_pct=0.002, eps_pct=0.001,
    )
    sp = out["structure_plan"]
    # Should pick 198 (first that is > spot*(1+eps) and distance >= 0.002)
    assert sp["T2"] == 198.0
    assert sp["T1"] is not None and sp["T1"] < 198.0
    assert out["target_basis"] == "SR_LEVEL"


def test_targets_fallback_to_atr_when_all_levels_too_close():
    """When no resistance meets min_distance_pct, use ATR fallback."""
    spot = 100.0
    atr = 2.0
    resistances_by_tf = {
        "daily": [{"level": 100.15, "distance_pct": 0.001}],  # 0.15% < 0.20% min
        "weekly": [],
        "monthly": [],
    }
    supports_by_tf = {"daily": [{"level": 99.85, "distance_pct": 0.001}], "weekly": [], "monthly": []}
    out = build_exit_plan_v235(
        spot, "CSP", atr, resistances_by_tf, supports_by_tf,
        min_distance_pct=0.002, eps_pct=0.001,
    )
    sp = out["structure_plan"]
    assert out["target_basis"] == "ATR_FALLBACK"
    assert out["level_source_timeframe"] is None
    assert sp["T1"] == 102.0 and sp["T2"] == 104.0 and sp["T3"] == 106.0


def test_targets_resistance_at_or_below_spot_skipped():
    """Resistance <= spot*(1+eps) is skipped; next valid one used."""
    spot = 50.0
    atr = 1.0
    resistances_by_tf = {
        "daily": [
            {"level": 50.0, "distance_pct": 0.01},   # at spot
            {"level": 50.04, "distance_pct": 0.01},   # within eps (0.001*50=0.05)
            {"level": 51.5, "distance_pct": 0.03},
        ],
        "weekly": [],
        "monthly": [],
    }
    supports_by_tf = {"daily": [], "weekly": [], "monthly": []}
    out = build_exit_plan_v235(
        spot, "CSP", atr, resistances_by_tf, supports_by_tf,
        min_distance_pct=0.002, eps_pct=0.001,
    )
    sp = out["structure_plan"]
    assert sp["T2"] == 51.5
    assert out["target_basis"] == "SR_LEVEL"


def test_cc_targets_monotonic_decreasing():
    """CC: T1 > T2 > T3 (all below spot)."""
    spot = 100.0
    atr = 2.0
    resistances_by_tf = {"daily": [{"level": 105.0, "distance_pct": 0.05}], "weekly": [], "monthly": []}
    supports_by_tf = {"daily": [{"level": 94.0, "distance_pct": 0.06}], "weekly": [], "monthly": []}
    out = build_exit_plan_v235(
        spot, "CC", atr, resistances_by_tf, supports_by_tf,
        min_distance_pct=0.002, eps_pct=0.001,
    )
    sp = out["structure_plan"]
    t1, t2, t3 = sp["T1"], sp["T2"], sp["T3"]
    assert t1 is not None and t2 is not None and t3 is not None
    assert t1 > t2 > t3
    assert out["target_basis"] == "SR_LEVEL"
