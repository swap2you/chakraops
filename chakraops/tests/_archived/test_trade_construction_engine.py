# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 4.1 trade construction engine: deterministic TradeProposal, risk-first rejection."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.trade_construction.engine import build_trade
from app.models.option_context import OptionContext
from app.models.trade_proposal import TradeProposal
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import SelectedSignal


def _make_candidate(
    symbol: str,
    signal_type: SignalType,
    *,
    underlying_price: float = 100.0,
    strike: float = 95.0,
    expiry: date | None = None,
    mid: float | None = 1.5,
    bid: float | None = 1.4,
    option_context: OptionContext | None = None,
) -> SignalCandidate:
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    exp = expiry or (as_of.date() + timedelta(days=30))
    return SignalCandidate(
        symbol=symbol,
        signal_type=signal_type,
        as_of=as_of,
        underlying_price=underlying_price,
        expiry=exp,
        strike=strike,
        option_right="PUT" if signal_type == SignalType.CSP else "CALL",
        bid=bid,
        ask=bid + 0.1 if bid is not None else None,
        mid=mid,
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


def _make_selected(candidate: SignalCandidate, score_total: float = 0.8) -> SelectedSignal:
    scored = ScoredSignalCandidate(
        candidate=candidate,
        score=SignalScore(total=score_total, components=[]),
        rank=1,
    )
    return SelectedSignal(scored=scored, selection_reason="top")


def _portfolio_config(account_balance: float = 100_000.0, max_risk_per_trade_pct: float = 1.0) -> dict:
    return {
        "account_balance": account_balance,
        "max_risk_per_trade_pct": max_risk_per_trade_pct,
        "max_active_positions": 5,
        "max_sector_positions": 2,
        "max_total_delta_exposure": 0.30,
    }


# --- CSP valid ---


def test_csp_valid_returns_proposal_not_rejected():
    """CSP with strike below 1sd, credit >= 0.5% notional, max_loss within budget -> rejected=False."""
    # underlying 100, expected_move_1sd 0.05 -> threshold_below = 95. Strike 94 < 95 ok.
    # notional = 94*100 = 9400, min_credit = 0.005*9400 = 47. Credit 150 >= 47. max_loss = 9400-150 = 9250; budget 1% of 100k = 1000 -> 9250 > 1000 so we'd reject on risk budget.
    # So use higher account or lower strike so max_loss fits. max_loss = 9400 - 150 = 9250. We need risk_budget >= 9250, so account_balance >= 9250/0.01 = 925000.
    underlying = 100.0
    strike = 94.0  # below 95 (1sd)
    expected_move = 0.05
    credit_per_contract = 150.0 / 100  # 1.5 per share -> 150 per contract
    notional = strike * 100
    max_loss = notional - 150.0  # 9400 - 150 = 9250
    account = 1_000_000.0  # 1% = 10000, so 9250 fits
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=expected_move)
    cand = _make_candidate("AAPL", SignalType.CSP, underlying_price=underlying, strike=strike, mid=1.5, bid=1.5)
    cand_with_ctx = _make_candidate(
        "AAPL", SignalType.CSP, underlying_price=underlying, strike=strike, mid=1.5, bid=1.5, option_context=ctx
    )
    selected = _make_selected(cand_with_ctx)
    config = _portfolio_config(account_balance=account)
    proposal = build_trade(selected, ctx, config)
    assert isinstance(proposal, TradeProposal)
    assert proposal.rejected is False
    assert proposal.rejection_reason is None
    assert proposal.symbol == "AAPL"
    assert proposal.strategy_type == "CSP"
    assert proposal.strikes == strike
    assert proposal.credit_estimate == 150.0
    assert proposal.max_loss == max_loss


def test_csp_invalid_strike_above_expected_move_rejected():
    """CSP with strike above 1sd threshold -> rejected with reason."""
    # underlying 100, expected_move 0.05 -> threshold 95. Strike 96 > 95 -> reject
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    cand = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=96.0, option_context=ctx)
    selected = _make_selected(cand)
    proposal = build_trade(selected, ctx, _portfolio_config(account_balance=1_000_000))
    assert proposal.rejected is True
    assert proposal.rejection_reason is not None
    assert "1sd" in proposal.rejection_reason or "threshold" in proposal.rejection_reason.lower()
    assert "96" in proposal.rejection_reason or "95" in proposal.rejection_reason


def test_csp_invalid_credit_below_half_percent_rejected():
    """CSP with credit < 0.5% of notional -> rejected."""
    # notional = 95*100 = 9500, min_credit = 47.5. Use credit 30 (mid=0.30).
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    cand = _make_candidate(
        "AAPL", SignalType.CSP, underlying_price=100.0, strike=94.0, mid=0.30, bid=0.30, option_context=ctx
    )
    selected = _make_selected(cand)
    proposal = build_trade(selected, ctx, _portfolio_config(account_balance=1_000_000))
    assert proposal.rejected is True
    assert proposal.rejection_reason is not None
    assert "0.5%" in proposal.rejection_reason or "notional" in proposal.rejection_reason.lower()


def test_csp_invalid_risk_budget_breach_rejected():
    """CSP max_loss > portfolio max risk per trade -> rejected."""
    # strike 94, credit 50 -> max_loss = 9400 - 50 = 9350. Budget 1% of 100k = 1000. 9350 > 1000 -> reject
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    cand = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=94.0, mid=0.5, bid=0.5, option_context=ctx)
    selected = _make_selected(cand)
    config = _portfolio_config(account_balance=100_000.0, max_risk_per_trade_pct=1.0)
    proposal = build_trade(selected, ctx, config)
    assert proposal.rejected is True
    assert proposal.rejection_reason is not None
    assert "risk budget" in proposal.rejection_reason.lower() or "exceeds" in proposal.rejection_reason.lower()


def test_csp_missing_expected_move_rejected():
    """CSP with no option_context or expected_move_1sd -> rejected (risk-first)."""
    cand = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=94.0, option_context=None)
    selected = _make_selected(cand)
    proposal = build_trade(selected, None, _portfolio_config())
    assert proposal.rejected is True
    assert proposal.rejection_reason is not None
    assert "expected_move_1sd" in proposal.rejection_reason


# --- Credit spread / CC ---


def test_cc_bear_call_spread_single_leg_rejected():
    """Single-leg CC (BearCallSpread) has unbounded max_loss -> rejected."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    # short call strike 106 >= 105 (1sd above) so move check passes; then single-leg -> unbounded max_loss
    cand = _make_candidate(
        "AAPL", SignalType.CC, underlying_price=100.0, strike=106.0, mid=1.0, bid=1.0, option_context=ctx
    )
    selected = _make_selected(cand)
    proposal = build_trade(selected, ctx, _portfolio_config())
    assert proposal.rejected is True
    assert proposal.strategy_type == "BearCallSpread"
    assert "unbounded" in proposal.rejection_reason.lower() or "spread" in proposal.rejection_reason.lower()


def test_cc_short_strike_inside_expected_move_rejected():
    """BearCallSpread short strike inside 1sd (below threshold) -> rejected."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)  # threshold above = 105
    cand = _make_candidate(
        "AAPL", SignalType.CC, underlying_price=100.0, strike=103.0, mid=1.0, option_context=ctx
    )
    selected = _make_selected(cand)
    proposal = build_trade(selected, ctx, _portfolio_config())
    assert proposal.rejected is True
    assert "103" in proposal.rejection_reason or "105" in proposal.rejection_reason or "1sd" in proposal.rejection_reason


def test_credit_spread_missing_expected_move_rejected():
    """Credit spread (CC) with no expected_move_1sd -> rejected."""
    cand = _make_candidate("AAPL", SignalType.CC, underlying_price=100.0, strike=106.0, option_context=None)
    selected = _make_selected(cand)
    proposal = build_trade(selected, None, _portfolio_config())
    assert proposal.rejected is True
    assert "expected_move_1sd" in proposal.rejection_reason


# --- Rejection reason shape ---


def test_rejection_reasons_asserted():
    """All rejection paths set rejected=True and a non-empty rejection_reason."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05)
    config_small_budget = _portfolio_config(account_balance=100_000, max_risk_per_trade_pct=1.0)

    # CSP risk budget
    c1 = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=94.0, mid=0.5, option_context=ctx)
    p1 = build_trade(_make_selected(c1), ctx, config_small_budget)
    assert p1.rejected
    assert p1.rejection_reason and len(p1.rejection_reason) > 0

    # CSP credit too low
    c2 = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=94.0, mid=0.2, option_context=ctx)
    p2 = build_trade(_make_selected(c2), ctx, _portfolio_config(account_balance=1_000_000))
    assert p2.rejected
    assert p2.rejection_reason and "0.5%" in p2.rejection_reason

    # CSP strike above 1sd
    c3 = _make_candidate("AAPL", SignalType.CSP, underlying_price=100.0, strike=96.0, option_context=ctx)
    p3 = build_trade(_make_selected(c3), ctx, _portfolio_config(account_balance=1_000_000))
    assert p3.rejected
    assert p3.rejection_reason
