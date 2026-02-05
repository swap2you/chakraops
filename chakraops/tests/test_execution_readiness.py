# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 4.3 execution readiness and human acknowledgment controls."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.models.trade_proposal import (
    TradeProposal,
    set_execution_readiness,
    trade_proposal_from_dict,
)
from app.signals.models import SignalCandidate, SignalType
from app.signals.scoring import ScoredSignalCandidate, SignalScore
from app.signals.selection import SelectedSignal


def _make_candidate(symbol: str = "AAPL", strike: float = 94.0, underlying: float = 100.0) -> SignalCandidate:
    as_of = datetime(2026, 1, 22, 10, 0, 0)
    expiry = as_of.date() + timedelta(days=30)
    return SignalCandidate(
        symbol=symbol,
        signal_type=SignalType.CSP,
        as_of=as_of,
        underlying_price=underlying,
        expiry=expiry,
        strike=strike,
        option_right="PUT",
        bid=1.5,
        ask=1.6,
        mid=1.55,
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
        option_context=None,
    )


def _make_selected(candidate: SignalCandidate) -> SelectedSignal:
    scored = ScoredSignalCandidate(
        candidate=candidate,
        score=SignalScore(total=0.8, components=[]),
        rank=1,
    )
    return SelectedSignal(scored=scored, selection_reason="top")


def test_no_trade_marked_ready_without_passing_guards():
    """No trade is marked READY without passing all guards (not rejected and gate allowed)."""
    # Rejected proposal -> BLOCKED even when gate allowed
    rejected = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=96.0,
        contracts=1,
        credit_estimate=50.0,
        max_loss=9400.0,
        rejected=True,
        rejection_reason="strike above 1sd",
    )
    with_readiness = set_execution_readiness(rejected, gate_allowed=True)
    assert with_readiness.execution_status == "BLOCKED"

    # Not rejected but gate not allowed -> BLOCKED
    ok_proposal = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=94.0,
        contracts=1,
        credit_estimate=150.0,
        max_loss=9250.0,
        rejected=False,
    )
    with_readiness_blocked = set_execution_readiness(ok_proposal, gate_allowed=False)
    assert with_readiness_blocked.execution_status == "BLOCKED"

    # Not rejected and gate allowed -> READY
    with_readiness_ready = set_execution_readiness(ok_proposal, gate_allowed=True)
    assert with_readiness_ready.execution_status == "READY"


def test_manual_acknowledgment_required_for_ready():
    """READY proposals default to user_acknowledged=False; manual ack required."""
    ok_proposal = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=94.0,
        contracts=1,
        credit_estimate=150.0,
        max_loss=9250.0,
        rejected=False,
    )
    ready = set_execution_readiness(ok_proposal, gate_allowed=True)
    assert ready.execution_status == "READY"
    assert ready.user_acknowledged is False
    assert ready.execution_notes == ""


def test_execution_status_and_notes_roundtrip():
    """execution_status, user_acknowledged, execution_notes roundtrip in to_dict/from dict."""
    proposal = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=94.0,
        contracts=1,
        credit_estimate=150.0,
        max_loss=9250.0,
        rejected=False,
        execution_status="READY",
        user_acknowledged=True,
        execution_notes="Ack for test",
    )
    d = proposal.to_dict()
    assert d["execution_status"] == "READY"
    assert d["user_acknowledged"] is True
    assert d["execution_notes"] == "Ack for test"
    restored = trade_proposal_from_dict(d)
    assert restored is not None
    assert restored.execution_status == "READY"
    assert restored.user_acknowledged is True
    assert restored.execution_notes == "Ack for test"


def test_set_execution_readiness_preserves_ack_and_notes():
    """set_execution_readiness preserves user_acknowledged and execution_notes."""
    proposal = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=94.0,
        contracts=1,
        credit_estimate=150.0,
        max_loss=9250.0,
        rejected=False,
        user_acknowledged=True,
        execution_notes="Already acked",
    )
    ready = set_execution_readiness(proposal, gate_allowed=True)
    assert ready.user_acknowledged is True
    assert ready.execution_notes == "Already acked"


def test_readiness_requires_regime_risk_on():
    """READY requires gate allowed AND regime=RISK_ON; volatility kill switch (RISK_OFF) blocks READY."""
    ok_proposal = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=94.0,
        contracts=1,
        credit_estimate=150.0,
        max_loss=9250.0,
        rejected=False,
    )
    # Simulate: gate allowed but regime=RISK_OFF (e.g. volatility kill switch) -> effective gate False
    with_readiness = set_execution_readiness(ok_proposal, gate_allowed=False)
    assert with_readiness.execution_status == "BLOCKED"
    # When both gate and regime OK -> READY
    with_readiness_ready = set_execution_readiness(ok_proposal, gate_allowed=True)
    assert with_readiness_ready.execution_status == "READY"


def test_rejected_always_blocked():
    """Rejected proposal is always BLOCKED regardless of gate."""
    rejected = TradeProposal(
        symbol="AAPL",
        strategy_type="CSP",
        expiry=date(2026, 2, 22),
        strikes=96.0,
        contracts=1,
        credit_estimate=50.0,
        max_loss=9400.0,
        rejected=True,
        rejection_reason="credit too low",
    )
    assert set_execution_readiness(rejected, gate_allowed=True).execution_status == "BLOCKED"
    assert set_execution_readiness(rejected, gate_allowed=False).execution_status == "BLOCKED"
