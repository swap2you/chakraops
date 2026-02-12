# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for data completeness execution guard (Phase 4.5.4)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.environment.data_completeness_guard import check_data_completeness
from app.models.option_context import OptionContext
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import SelectedSignal


def _make_selected(
    symbol: str = "AAPL",
    *,
    underlying_price: float = 100.0,
    bid: float | None = 1.0,
    mid: float | None = None,
    open_interest: int | None = 1000,
    option_context: OptionContext | None = None,
) -> SelectedSignal:
    """Build a minimal SelectedSignal for data completeness tests."""
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    expiry = as_of.date() + timedelta(days=30)
    cand = SignalCandidate(
        symbol=symbol,
        signal_type=SignalType.CSP,
        as_of=as_of,
        underlying_price=underlying_price,
        expiry=expiry,
        strike=95.0,
        option_right="PUT",
        bid=bid,
        ask=1.1,
        mid=mid,
        volume=1000,
        open_interest=open_interest,
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
    scored = ScoredSignalCandidate(
        candidate=cand,
        score=SignalScore(total=0.8, components=[]),
        rank=1,
    )
    return SelectedSignal(scored=scored, selection_reason="SELECTED_BY_POLICY")


def test_complete_data_pass():
    """When expected_move_1sd, underlying_price, bid/mid, and open_interest are present → pass."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    signal = _make_selected(option_context=ctx, bid=1.0, open_interest=500)
    reason = check_data_completeness(signal, ctx)
    assert reason is None


def test_complete_data_with_mid_pass():
    """When mid is present (no bid) and open_interest present → pass."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    signal = _make_selected(option_context=ctx, bid=None, mid=1.05, open_interest=500)
    reason = check_data_completeness(signal, ctx)
    assert reason is None


def test_missing_expected_move_1sd_blocked():
    """When option_context has no expected_move_1sd → DATA_INCOMPLETE."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=None)
    signal = _make_selected(option_context=ctx)
    reason = check_data_completeness(signal, ctx)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "expected_move_1sd" in reason.data.get("missing", [])


def test_missing_option_context_expected_move_blocked():
    """When option_context is None → expected_move_1sd missing."""
    signal = _make_selected(option_context=None)
    reason = check_data_completeness(signal, None)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "expected_move_1sd" in reason.data.get("missing", [])


def test_underlying_price_zero_blocked():
    """When underlying_price is 0 → DATA_INCOMPLETE."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    signal = _make_selected(option_context=ctx, underlying_price=0.0)
    reason = check_data_completeness(signal, ctx)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "underlying_price" in reason.data.get("missing", [])


def test_missing_bid_and_mid_blocked():
    """When both bid and mid are None → DATA_INCOMPLETE (bid_or_mid)."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    signal = _make_selected(option_context=ctx, bid=None, mid=None, open_interest=500)
    reason = check_data_completeness(signal, ctx)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "bid_or_mid" in reason.data.get("missing", [])


def test_missing_open_interest_blocked():
    """When open_interest is None → DATA_INCOMPLETE."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    signal = _make_selected(option_context=ctx, open_interest=None)
    reason = check_data_completeness(signal, ctx)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "open_interest" in reason.data.get("missing", [])


def test_expected_move_zero_blocked():
    """When expected_move_1sd is 0 → DATA_INCOMPLETE."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.0)
    signal = _make_selected(option_context=ctx)
    reason = check_data_completeness(signal, ctx)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    assert "expected_move_1sd" in reason.data.get("missing", [])


def test_multiple_missing():
    """When several fields missing → DATA_INCOMPLETE lists all."""
    signal = _make_selected(
        option_context=None,
        bid=None,
        mid=None,
        open_interest=None,
    )
    reason = check_data_completeness(signal, None)
    assert reason is not None
    assert reason.code == "DATA_INCOMPLETE"
    missing = reason.data.get("missing", [])
    assert "expected_move_1sd" in missing
    assert "bid_or_mid" in missing
    assert "open_interest" in missing
