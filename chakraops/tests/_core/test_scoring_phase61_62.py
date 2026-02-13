# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.1/6.2: Scoring, tiering, ranking (diagnostic only). No decision impact."""

from __future__ import annotations

import pytest

from app.core.scoring.signal_score import compute_signal_score
from app.core.scoring.tiering import assign_tier
from app.core.scoring.ranking import rank_candidates
from app.core.scoring.config import ACCOUNT_EQUITY_DEFAULT, AFFORDABILITY_PCT_100, AFFORDABILITY_PCT_0


def test_scoring_determinism():
    """Given fixed eligibility_trace + stage2_trace, composite_score equals expected."""
    el = {
        "mode_decision": "CSP",
        "regime": "UP",
        "rsi14": 50.0,
        "atr_pct": 0.02,
        "distance_to_support_pct": 0.01,
        "distance_to_resistance_pct": 0.03,
    }
    st2 = {"spot_used": 100.0, "selected_trade": {"spread_pct": 0.02, "oi": 5000}}
    out = compute_signal_score(el, st2, 100.0, account_equity=150_000)
    assert "composite_score" in out
    assert 0 <= out["composite_score"] <= 100
    # Same inputs -> same score
    out2 = compute_signal_score(el, st2, 100.0, account_equity=150_000)
    assert out["composite_score"] == out2["composite_score"]
    assert out["components"]["regime_score"] == 100.0
    assert out["components"]["affordability_score"] is not None


def test_affordability_high_notional_low_score():
    """With spot=1000 and account=150k, notional_pct high -> affordability_score low."""
    el = {"mode_decision": "CSP", "regime": "UP", "rsi14": 50, "atr_pct": 0.02}
    st2 = {"spot_used": 1000.0}
    out = compute_signal_score(el, st2, 1000.0, account_equity=150_000)
    notional_pct = out["notional_pct_of_account"]
    assert notional_pct is not None
    # 1000*100/150000 = 0.666 > 0.30 -> affordability 0
    assert notional_pct > 0.30
    assert out["components"]["affordability_score"] == 0.0


def test_affordability_low_notional_high_score():
    """With spot=30 and account=150k, notional_pct low -> affordability_score high."""
    el = {"mode_decision": "CSP", "regime": "UP", "rsi14": 50, "atr_pct": 0.02}
    st2 = {"spot_used": 30.0}
    out = compute_signal_score(el, st2, 30.0, account_equity=150_000)
    notional_pct = out["notional_pct_of_account"]
    assert notional_pct is not None
    # 30*100/150000 = 0.02 <= 5% -> affordability 100
    assert notional_pct <= AFFORDABILITY_PCT_100
    assert out["components"]["affordability_score"] == 100.0


def test_tiering_thresholds():
    """score 85 -> A, 70 -> B, 50 -> C, 30 -> NONE (when mode != NONE)."""
    assert assign_tier("CSP", 85) == "A"
    assert assign_tier("CSP", 80) == "A"
    assert assign_tier("CSP", 70) == "B"
    assert assign_tier("CSP", 60) == "B"
    assert assign_tier("CSP", 50) == "C"
    assert assign_tier("CSP", 40) == "C"
    assert assign_tier("CSP", 30) == "NONE"
    assert assign_tier("CSP", 0) == "NONE"
    assert assign_tier("NONE", 99) == "NONE"


def test_ranking_stability():
    """Given candidates A/B/C, order is correct with tie-breaks."""
    a = {"symbol": "A", "tier": "A", "score": {"composite_score": 85, "components": {"affordability_score": 80, "liquidity_score": 90}}}
    b = {"symbol": "B", "tier": "B", "score": {"composite_score": 70, "components": {"affordability_score": 70, "liquidity_score": 85}}}
    c = {"symbol": "C", "tier": "A", "score": {"composite_score": 82, "components": {"affordability_score": 75, "liquidity_score": 80}}}
    ranked = rank_candidates([c, b, a])
    assert len(ranked) == 3
    assert ranked[0]["symbol"] == "A"
    assert ranked[0]["priority_rank"] == 1
    assert ranked[1]["symbol"] == "C"
    assert ranked[2]["symbol"] == "B"
    assert ranked[1]["priority_rank"] == 2
    assert ranked[2]["priority_rank"] == 3


def test_ranking_tie_break_affordability():
    """Tertiary sort: affordability_score desc (expensive CSPs drop)."""
    high_aff = {"symbol": "X", "tier": "B", "score": {"composite_score": 65, "components": {"affordability_score": 90, "liquidity_score": 50}}}
    low_aff = {"symbol": "Y", "tier": "B", "score": {"composite_score": 65, "components": {"affordability_score": 50, "liquidity_score": 50}}}
    ranked = rank_candidates([low_aff, high_aff])
    assert ranked[0]["symbol"] == "X"
    assert ranked[1]["symbol"] == "Y"


def test_no_decision_impact():
    """Scoring does not change mode_decision or stage2 selection (regression-style)."""
    el = {"mode_decision": "CSP", "regime": "UP", "rsi14": 55, "atr_pct": 0.03}
    st2 = {"spot_used": 100, "selected_trade": {"strike": 98, "exp": "2025-03-21"}}
    out = compute_signal_score(el, st2, 100.0)
    # Score is computed; we do not modify el or st2
    assert el["mode_decision"] == "CSP"
    assert st2["selected_trade"]["strike"] == 98
    assert "composite_score" in out
    # assign_tier returns a string; does not mutate inputs
    tier = assign_tier("CSP", out["composite_score"])
    assert tier in ("A", "B", "C", "NONE")
    assert el["mode_decision"] == "CSP"


def test_mode_none_composite_still_exists():
    """If mode_decision == NONE, composite_score can still exist; tier is NONE."""
    el = {"mode_decision": "NONE", "rejection_reason_codes": ["FAIL_RSI_CSP"], "rsi14": 70}
    out = compute_signal_score(el, None, 100.0)
    assert "composite_score" in out
    assert out["composite_score"] is not None
    tier = assign_tier("NONE", out["composite_score"])
    assert tier == "NONE"


def test_missing_data_degrades_score():
    """Missing data -> degrade score and record missing_fields."""
    el = {"mode_decision": "CSP"}
    out = compute_signal_score(el, None, None)
    assert "missing_fields" in out
    assert len(out["missing_fields"]) >= 1
    assert "composite_score" in out
