# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 4.2 iron condor: generator, strategy gating, trade construction."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.core.market.stock_models import StockSnapshot
from app.core.trade_construction.engine import (
    _iron_condor_gate,
    build_iron_condor_trade,
)
from app.models.option_context import OptionContext
from app.models.trade_proposal import TradeProposal
from app.signals.adapters.theta_options_adapter import NormalizedOptionQuote
from app.signals.iron_condor import (
    IronCondorCandidate,
    generate_iron_condor_candidates,
)
from app.signals.models import SignalEngineConfig


def _stock_snapshot(symbol: str = "AAPL", price: float = 100.0) -> StockSnapshot:
    return StockSnapshot(
        symbol=symbol,
        price=price,
        bid=price - 0.01,
        ask=price + 0.01,
        volume=1_000_000,
        avg_volume=2_000_000,
        has_options=True,
        snapshot_time=datetime(2026, 1, 22, 10, 0, 0),
        data_source="THETA",
    )


def _base_config() -> SignalEngineConfig:
    return SignalEngineConfig(
        dte_min=7,
        dte_max=45,
        min_bid=0.05,
        min_open_interest=10,
        max_spread_pct=25.0,
    )


def _quote(
    underlying: str,
    expiry: date,
    strike: float,
    right: str,
    bid: float,
    ask: float | None = None,
) -> NormalizedOptionQuote:
    return NormalizedOptionQuote(
        underlying=underlying,
        expiry=expiry,
        strike=Decimal(str(strike)),
        right=right,
        bid=bid,
        ask=ask or bid + 0.05,
        last=None,
        volume=100,
        open_interest=100,
        as_of=datetime(2026, 1, 22, 10, 0, 0),
    )


# --- Valid condor (trade construction) ---


def test_iron_condor_valid_returns_proposal_not_rejected():
    """Iron condor with RISK_ON, IV 30-70, expected move < 40% width -> rejected=False."""
    # total_width = 110 - 90 = 20. expected move 1sd = 0.03 -> 3.0 dollars. 3.0 < 0.4 * 20 = 8 -> pass
    ctx = OptionContext(
        symbol="AAPL",
        expected_move_1sd=0.03,
        iv_rank=50.0,
    )
    ic = IronCondorCandidate(
        symbol="AAPL",
        expiry=date(2026, 2, 20),
        put_short_strike=90.0,
        put_long_strike=85.0,
        call_short_strike=110.0,
        call_long_strike=115.0,
        credit_put=80.0,
        credit_call=70.0,
        max_loss_put=420.0,
        max_loss_call=430.0,
        underlying_price=100.0,
        option_context=ctx,
    )
    portfolio_config = {
        "account_balance": 100_000.0,
        "max_risk_per_trade_pct": 1.0,
    }
    proposal = build_iron_condor_trade(ic, ctx, portfolio_config, "RISK_ON")
    assert isinstance(proposal, TradeProposal)
    assert proposal.rejected is False
    assert proposal.rejection_reason is None
    assert proposal.strategy_type == "IRON_CONDOR"
    assert proposal.credit_estimate == 150.0
    assert proposal.max_loss == 430.0


def test_iron_condor_rejected_due_to_expected_move():
    """Expected move >= 40% of total width -> rejected."""
    # total_width = 10. expected move 1sd = 0.05 -> 5 dollars. 5 >= 0.4 * 10 = 4 -> reject
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.05, iv_rank=50.0)
    ic = IronCondorCandidate(
        symbol="AAPL",
        expiry=date(2026, 2, 20),
        put_short_strike=95.0,
        put_long_strike=90.0,
        call_short_strike=105.0,
        call_long_strike=110.0,
        credit_put=50.0,
        credit_call=50.0,
        max_loss_put=450.0,
        max_loss_call=450.0,
        underlying_price=100.0,
        option_context=ctx,
    )
    portfolio_config = {"account_balance": 100_000.0, "max_risk_per_trade_pct": 1.0}
    proposal = build_iron_condor_trade(ic, ctx, portfolio_config, "RISK_ON")
    assert proposal.rejected is True
    assert proposal.rejection_reason is not None
    assert "40%" in proposal.rejection_reason or "width" in proposal.rejection_reason.lower()


def test_iron_condor_do_not_appear_in_trending_or_volatile_regimes():
    """Condors do NOT appear when regime != RISK_ON."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.02, iv_rank=50.0)
    ic = IronCondorCandidate(
        symbol="AAPL",
        expiry=date(2026, 2, 20),
        put_short_strike=90.0,
        put_long_strike=85.0,
        call_short_strike=110.0,
        call_long_strike=115.0,
        credit_put=80.0,
        credit_call=70.0,
        max_loss_put=420.0,
        max_loss_call=430.0,
        underlying_price=100.0,
    )
    portfolio_config = {"account_balance": 100_000.0, "max_risk_per_trade_pct": 1.0}
    for regime in ("RISK_OFF", "TRENDING", "VOLATILE", ""):
        proposal = build_iron_condor_trade(ic, ctx, portfolio_config, regime)
        assert proposal.rejected is True
        assert "regime" in proposal.rejection_reason.lower() or "RISK_ON" in proposal.rejection_reason


def test_iron_condor_rejected_iv_rank_below_30():
    """IV rank below 30 -> rejected."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.02, iv_rank=20.0)
    ic = IronCondorCandidate(
        symbol="AAPL",
        expiry=date(2026, 2, 20),
        put_short_strike=90.0,
        put_long_strike=85.0,
        call_short_strike=110.0,
        call_long_strike=115.0,
        credit_put=80.0,
        credit_call=70.0,
        max_loss_put=420.0,
        max_loss_call=430.0,
        underlying_price=100.0,
    )
    proposal = build_iron_condor_trade(ic, ctx, {"account_balance": 100_000.0}, "RISK_ON")
    assert proposal.rejected is True
    assert "30" in proposal.rejection_reason


def test_iron_condor_rejected_iv_rank_above_70():
    """IV rank above 70 -> rejected."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.02, iv_rank=80.0)
    ic = IronCondorCandidate(
        symbol="AAPL",
        expiry=date(2026, 2, 20),
        put_short_strike=90.0,
        put_long_strike=85.0,
        call_short_strike=110.0,
        call_long_strike=115.0,
        credit_put=80.0,
        credit_call=70.0,
        max_loss_put=420.0,
        max_loss_call=430.0,
        underlying_price=100.0,
    )
    proposal = build_iron_condor_trade(ic, ctx, {"account_balance": 100_000.0}, "RISK_ON")
    assert proposal.rejected is True
    assert "70" in proposal.rejection_reason


# --- Generator: valid condor ---


def test_generator_valid_condor():
    """Generator produces one IC when puts and calls form valid bull put + bear call spread."""
    expiry = date(2026, 2, 20)
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    options = [
        _quote("AAPL", expiry, 90.0, "PUT", 1.20, 1.25),
        _quote("AAPL", expiry, 85.0, "PUT", 0.50, 0.55),
        _quote("AAPL", expiry, 110.0, "CALL", 1.10, 1.15),
        _quote("AAPL", expiry, 115.0, "CALL", 0.45, 0.50),
    ]
    stock = _stock_snapshot("AAPL", 100.0)
    base_cfg = _base_config()
    candidates, exclusions = generate_iron_condor_candidates(stock, options, base_cfg)
    assert len(candidates) >= 1
    ic = candidates[0]
    assert ic.symbol == "AAPL"
    assert ic.expiry == expiry
    assert ic.put_short_strike > ic.put_long_strike
    assert ic.call_short_strike < ic.call_long_strike
    assert ic.credit_put > 0
    assert ic.credit_call > 0


# --- Generator: rejected due to one bad leg ---


def test_generator_rejected_due_to_one_bad_leg_no_put_spread():
    """No valid bull put spread (e.g. only one put below spot) -> exclusions, no candidate."""
    expiry = date(2026, 2, 20)
    options = [
        _quote("AAPL", expiry, 95.0, "PUT", 2.0),
        _quote("AAPL", expiry, 105.0, "CALL", 1.5),
        _quote("AAPL", expiry, 110.0, "CALL", 0.5),
    ]
    stock = _stock_snapshot("AAPL", 100.0)
    base_cfg = _base_config()
    candidates, exclusions = generate_iron_condor_candidates(stock, options, base_cfg)
    assert len(candidates) == 0
    codes = [e.code for e in exclusions]
    assert "IC_PUT_LEG_INVALID" in codes or "IC_INSUFFICIENT_STRIKES" in codes or "IC_NO_LIQUID_LEGS" in codes


def test_generator_rejected_due_to_one_bad_leg_no_call_spread():
    """No valid bear call spread (e.g. only one call above spot) -> exclusions, no candidate."""
    expiry = date(2026, 2, 20)
    options = [
        _quote("AAPL", expiry, 90.0, "PUT", 1.2),
        _quote("AAPL", expiry, 85.0, "PUT", 0.5),
        _quote("AAPL", expiry, 105.0, "CALL", 2.0),
    ]
    stock = _stock_snapshot("AAPL", 100.0)
    base_cfg = _base_config()
    candidates, exclusions = generate_iron_condor_candidates(stock, options, base_cfg)
    assert len(candidates) == 0
    codes = [e.code for e in exclusions]
    assert "IC_CALL_LEG_INVALID" in codes or "IC_INSUFFICIENT_STRIKES" in codes or "IC_NO_LIQUID_LEGS" in codes


# --- Gate helper ---


def test_iron_condor_gate_risk_on_required():
    """_iron_condor_gate rejects when regime != RISK_ON."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.02, iv_rank=50.0)
    allowed, reason = _iron_condor_gate(ctx, total_width=20.0, underlying=100.0, regime="RISK_OFF")
    assert allowed is False
    assert "RISK_ON" in reason


def test_iron_condor_gate_expected_move_under_40_percent():
    """_iron_condor_gate allows when expected move < 40% of width."""
    ctx = OptionContext(symbol="AAPL", expected_move_1sd=0.02, iv_rank=50.0)
    total_width = 20.0
    underlying = 100.0
    expected_dollars = 0.02 * 100  # 2.0
    threshold = 0.4 * 20  # 8.0
    assert expected_dollars < threshold
    allowed, reason = _iron_condor_gate(ctx, total_width=total_width, underlying=underlying, regime="RISK_ON")
    assert allowed is True
    assert reason is None
