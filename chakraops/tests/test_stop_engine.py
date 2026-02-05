# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for StopEngine: profit target, max loss, time stop, underlying breach, regime flip."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.core.exit.stop_engine import evaluate_stop
from app.core.models.position import Position
from app.models.exit_plan import ExitPlan


def _csp_position(
    symbol: str = "AAPL",
    strike: float = 150.0,
    dte: int = 30,
    premium_collected: float = 500.0,
    exit_plan: ExitPlan | None = None,
) -> Position:
    if exit_plan is None:
        exit_plan = ExitPlan(
            profit_target_pct=0.60,
            max_loss_multiplier=2.0,
            time_stop_days=14,
            underlying_stop_breach=True,
        )
    expiry = (date.today() + timedelta(days=dte)).isoformat()
    return Position(
        id="test-stop-1",
        symbol=symbol,
        position_type="CSP",
        strike=strike,
        expiry=expiry,
        contracts=1,
        premium_collected=premium_collected,
        entry_date=datetime.now().isoformat(),
        status="OPEN",
        state="OPEN",
        state_history=[],
        notes=None,
        exit_plan=exit_plan,
    )


class TestStopEngineProfitTarget:
    """Profit target: option value <= credit * (1 - profit_target_pct) -> ALERT (Phase 6.3: no auto-close)."""

    def test_profit_target_met(self):
        """When option value <= target close, return ALERT PROFIT_TARGET (event emitted)."""
        position = _csp_position(premium_collected=1000.0)
        # target = 1000 * (1 - 0.60) = 400; option_value 350 <= 400
        market_context = {
            "price": 155.0,
            "option_value": 350.0,
            "regime": "RISK_ON",
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "PROFIT_TARGET" in decision.reason_codes
        assert decision.urgency == "MEDIUM"

    def test_profit_target_exact_boundary(self):
        """Option value exactly at target close triggers ALERT."""
        position = _csp_position(premium_collected=1000.0)
        target = 1000.0 * (1.0 - 0.60)  # 400
        market_context = {
            "price": 155.0,
            "option_value": target,
            "regime": "RISK_ON",
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "PROFIT_TARGET" in decision.reason_codes

    def test_profit_target_not_met_hold(self):
        """Option value above target -> no profit trigger; continue to other rules."""
        position = _csp_position(premium_collected=1000.0)
        market_context = {
            "price": 155.0,
            "option_value": 500.0,  # > 400
            "regime": "RISK_ON",
            "dte": 20,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"
        assert "STOP_RULES_OK" in decision.reason_codes or "PROFIT_TARGET" not in decision.reason_codes


class TestStopEngineMaxLoss:
    """Max loss: option value >= credit * max_loss_multiplier -> ALERT (Phase 6.3: no auto-close)."""

    def test_max_loss_hit(self):
        """When option value >= credit * 2.0, return ALERT MAX_LOSS (event emitted)."""
        position = _csp_position(premium_collected=500.0)
        # threshold = 500 * 2 = 1000; option_value 1100 >= 1000
        market_context = {
            "price": 140.0,
            "option_value": 1100.0,
            "regime": "RISK_ON",
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "MAX_LOSS" in decision.reason_codes
        assert decision.urgency == "HIGH"

    def test_max_loss_exact_boundary(self):
        """Option value exactly at loss threshold triggers ALERT."""
        position = _csp_position(premium_collected=500.0)
        market_context = {
            "price": 145.0,
            "option_value": 1000.0,  # 500 * 2
            "regime": "RISK_ON",
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "MAX_LOSS" in decision.reason_codes

    def test_profit_target_before_max_loss(self):
        """Profit target is evaluated before max loss; profit wins when both could apply."""
        position = _csp_position(premium_collected=1000.0)
        # option_value 350: profit target 400 -> ALERT profit; loss threshold 2000 -> not hit
        market_context = {
            "price": 155.0,
            "option_value": 350.0,
            "regime": "RISK_ON",
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "PROFIT_TARGET" in decision.reason_codes


class TestStopEngineTimeStop:
    """Time stop: DTE <= time_stop_days -> ALERT (Phase 6.3: no auto-close)."""

    def test_time_stop_triggers(self):
        """When DTE <= 14, return ALERT TIME_STOP (event emitted)."""
        position = _csp_position(dte=10, premium_collected=500.0)
        market_context = {
            "price": 152.0,
            "option_value": 600.0,  # no profit/loss trigger
            "regime": "RISK_ON",
            "dte": 10,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "TIME_STOP" in decision.reason_codes
        assert decision.urgency == "HIGH"

    def test_time_stop_boundary(self):
        """DTE == time_stop_days triggers ALERT."""
        position = _csp_position(dte=14, premium_collected=500.0)
        market_context = {
            "price": 152.0,
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 14,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "TIME_STOP" in decision.reason_codes

    def test_time_stop_not_triggered(self):
        """DTE > time_stop_days does not trigger time stop."""
        position = _csp_position(dte=30, premium_collected=500.0)
        market_context = {
            "price": 152.0,
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 20,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"


class TestStopEngineUnderlyingBreach:
    """Underlying breach: close beyond short strike (CSP: below strike; CC: above)."""

    def test_csp_underlying_breach_below_strike(self):
        """CSP: price < strike -> CLOSE UNDERLYING_BREACH."""
        position = _csp_position(strike=150.0, premium_collected=500.0)
        market_context = {
            "price": 148.0,  # below strike
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "UNDERLYING_BREACH" in decision.reason_codes

    def test_csp_no_breach_above_strike(self):
        """CSP: price > strike -> no breach."""
        position = _csp_position(strike=150.0, premium_collected=500.0)
        market_context = {
            "price": 155.0,
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"

    def test_cc_underlying_breach_above_strike(self):
        """CC (non-CSP): price > strike -> ALERT UNDERLYING_BREACH (Phase 6.3: no auto-close)."""
        plan = ExitPlan(0.60, 2.0, 14, True)
        position = Position(
            id="test-cc-1",
            symbol="AAPL",
            position_type="SHARES",  # CC: short call strike; engine treats non-CSP as call -> breach when price > strike
            strike=155.0,
            expiry=(date.today() + timedelta(days=25)).isoformat(),
            contracts=1,
            premium_collected=300.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
            notes=None,
            exit_plan=plan,
        )
        market_context = {
            "price": 160.0,  # above strike
            "option_value": 400.0,
            "regime": "RISK_ON",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "UNDERLYING_BREACH" in decision.reason_codes

    def test_underlying_stop_breach_false_no_breach_exit(self):
        """When underlying_stop_breach is False, breach does not trigger (e.g. spread)."""
        plan = ExitPlan(0.60, 2.0, 14, underlying_stop_breach=False)
        position = _csp_position(strike=150.0, premium_collected=500.0, exit_plan=plan)
        market_context = {
            "price": 148.0,
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"


class TestStopEngineRegimeFlip:
    """Regime flip: current regime RISK_OFF -> CLOSE."""

    def test_regime_flip_close(self):
        """When regime is RISK_OFF, return CLOSE REGIME_FLIP."""
        position = _csp_position(premium_collected=500.0)
        market_context = {
            "price": 152.0,
            "option_value": 600.0,
            "regime": "RISK_OFF",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "ALERT"
        assert "REGIME_FLIP" in decision.reason_codes
        assert decision.urgency == "HIGH"

    def test_regime_risk_on_hold(self):
        """When regime is RISK_ON, no regime exit."""
        position = _csp_position(premium_collected=500.0)
        market_context = {
            "price": 152.0,
            "option_value": 600.0,
            "regime": "RISK_ON",
            "dte": 25,
        }
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"


class TestStopEngineNoExitPlan:
    """No exit plan or no credit -> HOLD."""

    def test_no_exit_plan_returns_hold(self):
        """Position without exit_plan returns HOLD with NO_EXIT_PLAN."""
        position = _csp_position(exit_plan=None)
        position = Position(
            id=position.id,
            symbol=position.symbol,
            position_type=position.position_type,
            strike=position.strike,
            expiry=position.expiry,
            contracts=position.contracts,
            premium_collected=position.premium_collected,
            entry_date=position.entry_date,
            status=position.status,
            state=position.state,
            state_history=position.state_history,
            notes=position.notes,
            exit_plan=None,
        )
        market_context = {"price": 152.0, "option_value": 600.0, "regime": "RISK_ON"}
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"
        assert "NO_EXIT_PLAN" in decision.reason_codes

    def test_no_credit_returns_hold(self):
        """Position with premium_collected <= 0 returns HOLD (skip stop rules)."""
        position = _csp_position(premium_collected=0.0)
        market_context = {"price": 152.0, "option_value": 100.0, "regime": "RISK_OFF"}
        decision = evaluate_stop(position, market_context)
        assert decision.action == "HOLD"
        assert "NO_CREDIT" in decision.reason_codes


class TestStopEngineActionEngineIntegration:
    """Action engine calls StopEngine first; exit triggers override later rules."""

    def test_stop_engine_close_overrides_premium_70(self):
        """When StopEngine returns ALERT (e.g. profit target), action engine returns that ALERT (Phase 6.3)."""
        from app.core.action_engine import evaluate_position_action
        position = _csp_position(premium_collected=1000.0)
        # Profit target met; also premium_collected_pct could be 70% for legacy rule
        market_context = {
            "price": 155.0,
            "option_value": 350.0,  # profit target met
            "regime": "RISK_ON",
            "EMA50": 152.0,
            "EMA200": 150.0,
            "premium_collected_pct": 70.0,
        }
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "ALERT"
        assert "PROFIT_TARGET" in decision.reason_codes

    def test_stop_engine_hold_then_legacy_rules(self):
        """When StopEngine returns HOLD (no exit plan), legacy rules run; premium 70% triggers CLOSE."""
        from app.core.action_engine import evaluate_position_action
        # Position with no exit_plan so stop returns HOLD; then legacy rule premium 70% triggers CLOSE
        position = Position(
            id="legacy-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=1050.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
            notes=None,
            exit_plan=None,
        )
        market_context = {
            "price": 155.0,
            "EMA50": 152.0,
            "EMA200": 150.0,
            "regime": "RISK_ON",
            "premium_collected_pct": 70.0,
        }
        decision = evaluate_position_action(position, market_context)
        assert decision.action == "CLOSE"
        assert "PREMIUM_70_PCT" in decision.reason_codes
