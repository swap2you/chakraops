# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for options context gating (Phase 3.2): IV rank, expected move, event proximity."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.option_context import OptionContext
from app.signals.context_gating import (
    ContextGateConfig,
    apply_context_gate,
    _check_context_gate,
)
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import SelectionConfig, select_signals


def _make_scored(
    symbol: str,
    signal_type: SignalType,
    score_total: float,
    rank: int,
    *,
    underlying_price: float = 100.0,
    strike: float = 95.0,
    option_context: OptionContext | None = None,
) -> ScoredSignalCandidate:
    """Build a minimal scored candidate with optional option_context."""
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    expiry = as_of.date() + timedelta(days=30)
    cand = SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=as_of,
        underlying_price=underlying_price,
        expiry=expiry,
        strike=strike,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=1.0,
        ask=1.1,
        mid=None,
        volume=1000,
        open_interest=1000,
        delta=None,
        prob_otm=None,
        iv_rank=None,
        iv=None,
        annualized_yield=None,
        raw_yield=None,
        max_profit=None,
        collateral=None,
        option_context=option_context,
    )
    return ScoredSignalCandidate(
        candidate=cand,
        score=SignalScore(total=score_total, components=[]),
        rank=rank,
    )


def test_candidates_carry_option_context():
    """Candidates can carry option_context attribute."""
    ctx = OptionContext(
        symbol="AAPL",
        expected_move_1sd=0.05,
        iv_rank=50.0,
        iv_percentile=55.0,
        term_structure_slope=-0.02,
        skew_metric=-0.06,
        days_to_earnings=14,
        event_flags=[],
    )
    scored = _make_scored("AAPL", SignalType.CSP, 0.8, 1, option_context=ctx)
    assert scored.candidate.option_context is not None
    assert scored.candidate.option_context.symbol == "AAPL"
    assert scored.candidate.option_context.iv_rank == 50.0


def test_iv_rank_low_sell_excluded():
    """Selling (CSP) when IV rank below min is excluded with iv_rank_low_sell."""
    ctx = OptionContext(symbol="AAPL", iv_rank=5.0, iv_percentile=10.0)
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is not None
    assert reason.code == "iv_rank_low_sell"
    assert reason.data.get("iv_rank") == 5.0

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 0
    assert len(exclusions) == 1
    assert exclusions[0].code == "iv_rank_low_sell"


def test_iv_rank_high_sell_excluded():
    """Selling (CSP) when IV rank above max is excluded with iv_rank_high_sell."""
    ctx = OptionContext(symbol="AAPL", iv_rank=95.0)
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is not None
    assert reason.code == "iv_rank_high_sell"

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 0
    assert exclusions[0].code == "iv_rank_high_sell"


def test_iv_rank_moderate_sell_passes():
    """Selling when IV rank in [10, 90] passes context gate (no expected-move/event failure)."""
    ctx = OptionContext(symbol="AAPL", iv_rank=50.0)
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is None

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 1
    assert len(exclusions) == 0


def test_expected_move_exceeds_strike_distance_excluded():
    """Block when expected 1sd move (dollars) > distance from underlying to short strike."""
    # Underlying 100, strike 95 -> distance 5. Expected move 10% -> 10 dollars > 5 -> block
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.10)
    scored = _make_scored(
        "AAPL", SignalType.CSP, 0.9, 1,
        underlying_price=100.0,
        strike=95.0,
        option_context=ctx,
    )
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is not None
    assert reason.code == "expected_move_exceeds_strike_distance"
    assert reason.data.get("expected_move_dollars") == 10.0
    assert reason.data.get("distance_to_strike") == 5.0

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 0
    assert exclusions[0].code == "expected_move_exceeds_strike_distance"


def test_expected_move_within_strike_distance_passes():
    """Pass when expected move <= distance to strike."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.03)  # 3% of 100 = 3; distance 5
    scored = _make_scored(
        "AAPL", SignalType.CSP, 0.9, 1,
        underlying_price=100.0,
        strike=95.0,
        option_context=ctx,
    )
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is None


def test_event_within_window_earnings_excluded():
    """Block when days_to_earnings within dte_event_window."""
    ctx = OptionContext(symbol="AAPL", days_to_earnings=3)
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=False,
    )
    reason = _check_context_gate(scored, config)
    assert reason is not None
    assert reason.code == "event_within_window"
    assert reason.data.get("days_to_earnings") == 3

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 0
    assert exclusions[0].code == "event_within_window"


def test_event_within_window_event_flags_excluded():
    """Block when event_flags non-empty and dte_event_window > 0."""
    ctx = OptionContext(symbol="AAPL", event_flags=["FOMC"])
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=False,
    )
    reason = _check_context_gate(scored, config)
    assert reason is not None
    assert reason.code == "event_within_window"
    assert "FOMC" in (reason.data.get("event_flags") or [])


def test_no_option_context_passes_gate():
    """Candidates without option_context pass context gate (best-effort)."""
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=None)
    config = ContextGateConfig(
        iv_rank_min_sell_pct=10.0,
        iv_rank_max_sell_pct=90.0,
        iv_rank_max_buy_pct=70.0,
        dte_event_window=7,
        expected_move_gate=True,
    )
    reason = _check_context_gate(scored, config)
    assert reason is None

    passed, exclusions = apply_context_gate([scored], config)
    assert len(passed) == 1
    assert len(exclusions) == 0


def test_select_signals_context_gate_exclusion_reasons():
    """select_signals with context_gate returns exclusion reasons for filtered candidates."""
    ctx_low_iv = OptionContext(symbol="AAPL", iv_rank=5.0)
    ctx_ok = OptionContext(symbol="MSFT", iv_rank=50.0)
    scored_list = [
        _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx_low_iv),
        _make_scored("MSFT", SignalType.CSP, 0.8, 2, option_context=ctx_ok),
    ]
    config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
        min_confidence_threshold=None,
        context_gate=ContextGateConfig(
            iv_rank_min_sell_pct=10.0,
            iv_rank_max_sell_pct=90.0,
            iv_rank_max_buy_pct=70.0,
            dte_event_window=7,
            expected_move_gate=False,
        ),
    )
    selected, exclusions = select_signals(scored_list, config)
    assert len(selected) == 1
    assert selected[0].scored.candidate.symbol == "MSFT"
    assert len(exclusions) == 1
    assert exclusions[0].code == "iv_rank_low_sell"
    assert exclusions[0].data.get("symbol") == "AAPL"


def test_context_gate_disabled_when_none():
    """When context_gate is None, no context filtering; all pass (subject to other caps)."""
    ctx = OptionContext(symbol="AAPL", iv_rank=5.0)
    scored = _make_scored("AAPL", SignalType.CSP, 0.9, 1, option_context=ctx)
    config = SelectionConfig(
        max_total=10,
        max_per_symbol=2,
        max_per_signal_type=None,
        min_score=0.0,
        min_confidence_threshold=None,
        context_gate=None,
    )
    selected, exclusions = select_signals([scored], config)
    assert len(selected) == 1
    assert len(exclusions) == 0
