# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for strategy selection (Phase 3.3): IV rank and term structure bias."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.option_context import OptionContext
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import (
    ScoringConfig,
    ScoredSignalCandidate,
    SignalScore,
    score_signals,
    _compute_strategy_preference_score,
)


def _make_candidate(
    symbol: str,
    signal_type: SignalType,
    *,
    option_context: OptionContext | None = None,
) -> SignalCandidate:
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    expiry = as_of.date() + timedelta(days=30)
    return SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=as_of,
        underlying_price=100.0,
        expiry=expiry,
        strike=95.0,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=1.0,
        ask=1.1,
        mid=1.05,
        volume=1000,
        open_interest=1000,
        delta=None,
        prob_otm=None,
        iv_rank=None,
        iv=None,
        option_context=option_context,
    )


def _config_with_strategy_weight(weight: float = 0.2) -> ScoringConfig:
    return ScoringConfig(
        premium_weight=0.25,
        dte_weight=0.25,
        spread_weight=0.0,
        otm_weight=0.0,
        liquidity_weight=0.25,
        context_weight=0.0,
        strategy_preference_weight=weight,
        strategy_iv_rank_high_pct=60.0,
        strategy_iv_rank_low_pct=20.0,
        strategy_term_slope_backwardation_min=0.0,
        strategy_term_slope_contango_max=0.0,
    )


def _get_component(scored: ScoredSignalCandidate, name: str) -> float | None:
    for c in scored.score.components:
        if c.name == name:
            return c.value
    return None


# --- Strategy preference score (IV rank) ---


def test_high_iv_rank_prefers_credit():
    """When IV rank > 60%, credit (CSP/CC) gets high strategy preference score."""
    ctx_high = OptionContext(symbol="AAPL", iv_rank=70.0)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_high)
    config = _config_with_strategy_weight(0.2)
    score = _compute_strategy_preference_score(cand, config)
    assert score >= 0.95
    assert score <= 1.0


def test_low_iv_rank_disprefers_credit():
    """When IV rank < 20%, credit gets low strategy preference (debit preferred later)."""
    ctx_low = OptionContext(symbol="AAPL", iv_rank=10.0)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_low)
    config = _config_with_strategy_weight(0.2)
    score = _compute_strategy_preference_score(cand, config)
    assert score >= 0.0
    assert score <= 0.2


def test_mid_iv_rank_linear():
    """IV rank between 20 and 60 gives score between 0 and 1."""
    ctx_mid = OptionContext(symbol="AAPL", iv_rank=40.0)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_mid)
    config = _config_with_strategy_weight(0.2)
    score = _compute_strategy_preference_score(cand, config)
    assert 0.4 <= score <= 0.6


def test_no_option_context_neutral():
    """No option_context -> strategy preference 0.5 (neutral)."""
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=None)
    config = _config_with_strategy_weight(0.2)
    score = _compute_strategy_preference_score(cand, config)
    assert score == 0.5


def test_cc_also_gets_high_score_when_iv_high():
    """CC (credit) also gets high strategy preference when IV rank high."""
    ctx_high = OptionContext(symbol="MSFT", iv_rank=65.0)
    cand = _make_candidate("MSFT", SignalType.CC, option_context=ctx_high)
    config = _config_with_strategy_weight(0.2)
    score = _compute_strategy_preference_score(cand, config)
    assert score >= 0.95


# --- Term structure and skew ---


def test_term_structure_backwardation_boosts_credit():
    """Positive term-structure slope (backwardation) adds small boost for credit."""
    # Use iv_rank 40 so base = 0.5; backwardation adds +0.05
    ctx = OptionContext(symbol="AAPL", iv_rank=40.0, term_structure_slope=0.02)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx)
    config = _config_with_strategy_weight(0.2)
    score_back = _compute_strategy_preference_score(cand, config)
    ctx_no_slope = OptionContext(symbol="AAPL", iv_rank=40.0)
    cand_no_slope = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_no_slope)
    score_no_slope = _compute_strategy_preference_score(cand_no_slope, config)
    assert score_back >= score_no_slope
    assert score_back >= 0.5


def test_term_structure_contango_reduces_credit():
    """Negative term-structure slope (contango) reduces credit preference."""
    ctx = OptionContext(symbol="AAPL", iv_rank=40.0, term_structure_slope=-0.03)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx)
    config = _config_with_strategy_weight(0.2)
    score_contango = _compute_strategy_preference_score(cand, config)
    ctx_no_slope = OptionContext(symbol="AAPL", iv_rank=40.0)
    cand_no_slope = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_no_slope)
    score_no_slope = _compute_strategy_preference_score(cand_no_slope, config)
    assert score_contango <= score_no_slope
    assert score_contango >= 0.4


def test_balanced_skew_boosts():
    """Balanced skew (small abs) adds small boost."""
    ctx_balanced = OptionContext(symbol="AAPL", iv_rank=40.0, skew_metric=0.02)
    cand_balanced = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_balanced)
    config = _config_with_strategy_weight(0.2)
    score_balanced = _compute_strategy_preference_score(cand_balanced, config)
    ctx_no_skew = OptionContext(symbol="AAPL", iv_rank=40.0)
    cand_no_skew = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_no_skew)
    score_no_skew = _compute_strategy_preference_score(cand_no_skew, config)
    assert score_balanced >= score_no_skew
    assert score_balanced >= 0.5


# --- Full scoring: correct strategy chosen ---


def test_scoring_ranks_high_iv_credit_above_low_iv():
    """With strategy_preference_weight > 0, high-IV credit ranks above low-IV credit (same other scores)."""
    ctx_high = OptionContext(symbol="AAPL", iv_rank=70.0)
    ctx_low = OptionContext(symbol="AAPL", iv_rank=15.0)
    cand_high = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_high)
    cand_low = _make_candidate("AAPL", SignalType.CSP, option_context=ctx_low)
    config = _config_with_strategy_weight(0.2)
    scored = score_signals([cand_high, cand_low], config)
    assert len(scored) == 2
    strat_high = _get_component(scored[0], "strategy_preference_score")
    strat_low = _get_component(scored[1], "strategy_preference_score")
    assert strat_high is not None and strat_low is not None
    assert strat_high > strat_low
    # First in list is highest total score; high IV should rank first
    assert scored[0].candidate.option_context is not None
    assert (scored[0].candidate.option_context.iv_rank or 0) > (scored[1].candidate.option_context.iv_rank or 0)


def test_strategy_preference_component_present_when_weight_nonzero():
    """strategy_preference_score component is present when strategy_preference_weight > 0."""
    ctx = OptionContext(symbol="AAPL", iv_rank=50.0)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx)
    config = _config_with_strategy_weight(0.15)
    scored = score_signals([cand], config)
    assert len(scored) == 1
    val = _get_component(scored[0], "strategy_preference_score")
    assert val is not None
    assert 0.0 <= val <= 1.0


def test_strategy_preference_zero_weight_no_effect():
    """When strategy_preference_weight=0, strategy preference does not change relative ranking of same-context candidates."""
    ctx = OptionContext(symbol="AAPL", iv_rank=70.0)
    cand = _make_candidate("AAPL", SignalType.CSP, option_context=ctx)
    config = ScoringConfig(
        premium_weight=0.5,
        dte_weight=0.25,
        spread_weight=0.0,
        otm_weight=0.0,
        liquidity_weight=0.25,
        context_weight=0.0,
        strategy_preference_weight=0.0,
    )
    scored = score_signals([cand], config)
    assert len(scored) == 1
    comp_names = [c.name for c in scored[0].score.components]
    assert "strategy_preference_score" in comp_names
    # Value still computed but weight 0 so no effect on total
    val = _get_component(scored[0], "strategy_preference_score")
    assert val is not None


def test_multiple_context_scenarios_correct_ordering():
    """Simulate multiple contexts: high IV CSP ranks first, low IV CSP last (same symbol/type)."""
    contexts = [
        OptionContext(symbol="AAPL", iv_rank=75.0),
        OptionContext(symbol="AAPL", iv_rank=40.0),
        OptionContext(symbol="AAPL", iv_rank=10.0),
    ]
    candidates = [
        _make_candidate("AAPL", SignalType.CSP, option_context=ctx)
        for ctx in contexts
    ]
    config = _config_with_strategy_weight(0.25)
    scored = score_signals(candidates, config)
    assert len(scored) == 3
    # Order by total score descending; high IV should be first, low IV last
    iv_ranks = [
        (scored[i].candidate.option_context.iv_rank or 0)
        for i in range(3)
    ]
    assert iv_ranks[0] == 75.0
    assert iv_ranks[1] == 40.0
    assert iv_ranks[2] == 10.0
