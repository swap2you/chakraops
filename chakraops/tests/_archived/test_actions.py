# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for action engine."""

import pytest
from datetime import date, datetime, timedelta

from app.core.models.position import Position
from app.core.engine.actions import (
    ActionType,
    Urgency,
    ActionDecision,
    RollPlan,
    decide_position_action,
)


class TestTerminalStates:
    """Test actions for terminal/non-actionable states."""
    
    def test_closed_position_returns_hold(self):
        """Test that CLOSED position returns HOLD action."""
        position = Position(
            id="test-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry="2026-03-21",
            contracts=1,
            premium_collected=300.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.HOLD
        assert decision.urgency == Urgency.LOW
        assert "Position not actionable" in decision.reasons
        assert len(decision.reasons) > 0
    
    def test_assigned_position_returns_hold(self):
        """Test that ASSIGNED position returns HOLD action."""
        position = Position(
            id="test-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry="2026-04-15",
            contracts=2,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="ASSIGNED",
            state="ASSIGNED",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.HOLD
        assert decision.urgency == Urgency.LOW
        assert "Position not actionable" in decision.reasons


class TestDTE:
    """Test DTE-based roll decisions."""
    
    def test_dte_7_days_returns_roll_high(self):
        """Test that position with DTE <= 7 returns ROLL (HIGH)."""
        # Expiry 7 days from today
        expiry_date = date.today() + timedelta(days=7)
        
        position = Position(
            id="test-3",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.ROLL
        assert decision.urgency == Urgency.HIGH
        assert "Expiry within 7 days" in decision.reasons
    
    def test_dte_5_days_returns_roll_high(self):
        """Test that position with DTE = 5 returns ROLL (HIGH)."""
        expiry_date = date.today() + timedelta(days=5)
        
        position = Position(
            id="test-4",
            symbol="AMZN",
            position_type="CSP",
            strike=100.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=200.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.ROLL
        assert decision.urgency == Urgency.HIGH
    
    def test_dte_8_days_does_not_trigger_roll(self):
        """Test that position with DTE = 8 does not trigger roll."""
        expiry_date = date.today() + timedelta(days=8)
        
        position = Position(
            id="test-5",
            symbol="META",
            position_type="CSP",
            strike=250.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=350.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        # Should not be ROLL (will be HOLD or CLOSE based on other rules)
        assert decision.action != ActionType.ROLL or decision.urgency != Urgency.HIGH


class TestPremiumCapture:
    """Test premium capture-based close decisions."""
    
    def test_premium_65_percent_returns_close_medium(self):
        """Test that premium >= 65% returns CLOSE (MEDIUM)."""
        # Position with 65% premium captured
        # premium_collected = 65% of strike * 100
        strike = 150.0
        contracts = 1
        premium_collected = (strike * 100) * 0.65  # 65% of max premium
        
        position = Position(
            id="test-6",
            symbol="GOOGL",
            position_type="CSP",
            strike=strike,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=contracts,
            premium_collected=premium_collected,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.CLOSE
        assert decision.urgency == Urgency.MEDIUM
        assert any("65%" in reason for reason in decision.reasons)
    
    def test_premium_70_percent_returns_close_medium(self):
        """Test that premium >= 70% returns CLOSE (MEDIUM)."""
        strike = 200.0
        contracts = 1
        premium_collected = (strike * 100) * 0.70  # 70% of max premium
        
        position = Position(
            id="test-7",
            symbol="TSLA",
            position_type="CSP",
            strike=strike,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=contracts,
            premium_collected=premium_collected,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.CLOSE
        assert decision.urgency == Urgency.MEDIUM
    
    def test_premium_64_percent_does_not_trigger_close(self):
        """Test that premium < 65% does not trigger CLOSE."""
        strike = 150.0
        contracts = 1
        premium_collected = (strike * 100) * 0.64  # 64% of max premium
        
        position = Position(
            id="test-8",
            symbol="SPY",
            position_type="CSP",
            strike=strike,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=contracts,
            premium_collected=premium_collected,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        # Should not be CLOSE (will be HOLD)
        assert decision.action != ActionType.CLOSE or decision.urgency != Urgency.MEDIUM
    
    def test_premium_from_market_ctx(self):
        """Test that premium_collected_pct from market_ctx is used."""
        position = Position(
            id="test-9",
            symbol="QQQ",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=100.0,  # Low premium, but market_ctx has high %
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {"premium_collected_pct": 70.0}
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.CLOSE
        assert decision.urgency == Urgency.MEDIUM


class TestDefaultHold:
    """Test default HOLD behavior."""
    
    def test_default_hold_low_urgency(self):
        """Test that positions without triggers return HOLD (LOW)."""
        position = Position(
            id="test-10",
            symbol="IWM",
            position_type="CSP",
            strike=180.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),  # DTE > 7
            contracts=1,
            premium_collected=(180.0 * 100) * 0.50,  # 50% premium (< 65%)
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        assert decision.action == ActionType.HOLD
        assert decision.urgency == Urgency.LOW
        assert len(decision.reasons) > 0
        assert len(decision.next_steps) > 0


class TestActionDecisionStructure:
    """Test ActionDecision dataclass structure."""
    
    def test_action_decision_has_all_fields(self):
        """Test that ActionDecision has all required fields."""
        decision = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["Test reason"],
            next_steps=["Test step"],
            computed_at=datetime.now(),
        )
        
        assert decision.action == ActionType.HOLD
        assert decision.urgency == Urgency.LOW
        assert isinstance(decision.reasons, list)
        assert isinstance(decision.next_steps, list)
        assert isinstance(decision.computed_at, datetime)


class TestRollPlan:
    """Test roll plan functionality."""
    
    def test_roll_plan_exists_when_roll_action(self):
        """Test that roll_plan is populated when action is ROLL."""
        expiry_date = date.today() + timedelta(days=5)
        
        position = Position(
            id="test-roll-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=300.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "underlying_price": 145.0,
            "atr_pct": 0.03,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ROLL
        assert decision.roll_plan is not None
        assert isinstance(decision.roll_plan, RollPlan)
    
    def test_roll_plan_suggested_expiry_in_range(self):
        """Test that suggested_expiry is within 30-45 days."""
        expiry_date = date.today() + timedelta(days=6)
        
        position = Position(
            id="test-roll-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "underlying_price": 195.0,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        suggested_expiry = decision.roll_plan.suggested_expiry
        
        today = date.today()
        days_from_today = (suggested_expiry - today).days
        
        assert 30 <= days_from_today <= 45, f"Expiry {days_from_today} days out not in range [30, 45]"
    
    def test_roll_plan_defensive_roll_type(self):
        """Test that defensive roll type is used when underlying < strike."""
        expiry_date = date.today() + timedelta(days=4)
        
        position = Position(
            id="test-roll-3",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "underlying_price": 280.0,  # Below strike
            "atr_pct": 0.04,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        assert decision.roll_plan.roll_type == "defensive"
        assert "defensive" in decision.roll_plan.notes[0].lower()
    
    def test_roll_plan_out_roll_type(self):
        """Test that out roll type is used when underlying >= strike."""
        expiry_date = date.today() + timedelta(days=3)
        
        position = Position(
            id="test-roll-4",
            symbol="AMZN",
            position_type="CSP",
            strike=100.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=200.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "underlying_price": 105.0,  # Above strike
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        assert decision.roll_plan.roll_type == "out"
        assert "out" in decision.roll_plan.notes[0].lower()
    
    def test_roll_plan_suggested_strike_less_than_underlying(self):
        """Test that suggested_strike is less than underlying_price."""
        expiry_date = date.today() + timedelta(days=2)
        
        position = Position(
            id="test-roll-5",
            symbol="META",
            position_type="CSP",
            strike=250.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=350.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        underlying_price = 240.0
        market_ctx = {
            "underlying_price": underlying_price,
            "atr_pct": 0.03,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        suggested_strike = decision.roll_plan.suggested_strike
        
        assert suggested_strike < underlying_price, \
            f"Suggested strike {suggested_strike} should be less than underlying {underlying_price}"
    
    def test_roll_plan_defensive_strike_calculation(self):
        """Test defensive strike calculation: max(underlying * 0.90, underlying - 2*ATR)."""
        expiry_date = date.today() + timedelta(days=1)
        
        position = Position(
            id="test-roll-6",
            symbol="GOOGL",
            position_type="CSP",
            strike=120.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=250.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        underlying_price = 100.0
        atr_pct = 0.05  # 5%
        market_ctx = {
            "underlying_price": underlying_price,
            "atr_pct": atr_pct,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        assert decision.roll_plan.roll_type == "defensive"
        
        # Calculate expected strike
        atr_proxy = underlying_price * atr_pct
        option1 = underlying_price * 0.90  # 90.0
        option2 = underlying_price - (2 * atr_proxy)  # 100 - 10 = 90.0
        expected_strike = max(option1, option2)
        
        # Allow for rounding to nearest $0.50
        assert abs(decision.roll_plan.suggested_strike - expected_strike) <= 0.5
    
    def test_roll_plan_out_strike_calculation(self):
        """Test out strike calculation: underlying * 0.95."""
        expiry_date = date.today() + timedelta(days=7)
        
        position = Position(
            id="test-roll-7",
            symbol="TSLA",
            position_type="CSP",
            strike=180.0,
            expiry=expiry_date.isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        underlying_price = 200.0
        market_ctx = {
            "underlying_price": underlying_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.roll_plan is not None
        assert decision.roll_plan.roll_type == "out"
        
        expected_strike = underlying_price * 0.95  # 190.0
        
        # Allow for rounding to nearest $0.50
        assert abs(decision.roll_plan.suggested_strike - expected_strike) <= 0.5
    
    def test_roll_plan_no_roll_plan_for_non_roll_actions(self):
        """Test that roll_plan is None for non-ROLL actions."""
        position = Position(
            id="test-roll-8",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=(400.0 * 100) * 0.50,  # 50% premium
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        decision = decide_position_action(position, {})
        
        # Should be HOLD (not ROLL), so no roll_plan
        assert decision.action == ActionType.HOLD
        assert decision.roll_plan is None


class TestRiskOverrides:
    """Test risk override functionality."""
    
    def test_risk_off_close_enabled_returns_close(self):
        """Test that RISK_OFF with CLOSE_ENABLED returns CLOSE (HIGH)."""
        from app.core.config import risk_overrides
        import app.core.engine.actions as actions_module
        
        # Temporarily enable RISK_OFF_CLOSE_ENABLED
        original_value = risk_overrides.RISK_OFF_CLOSE_ENABLED
        risk_overrides.RISK_OFF_CLOSE_ENABLED = True
        actions_module.RISK_OFF_CLOSE_ENABLED = True
        
        try:
            position = Position(
                id="test-risk-1",
                symbol="AAPL",
                position_type="CSP",
                strike=150.0,
                expiry=(date.today() + timedelta(days=30)).isoformat(),
                contracts=1,
                premium_collected=300.0,
                entry_date=datetime.now().isoformat(),
                status="OPEN",
                state="OPEN",
                state_history=[],
            )
            
            market_ctx = {
                "regime": "RISK_OFF",
            }
            
            decision = decide_position_action(position, market_ctx)
            
            assert decision.action == ActionType.CLOSE
            assert decision.urgency == Urgency.HIGH
            assert "RISK_OFF" in decision.reasons[0]
        finally:
            # Restore original value
            risk_overrides.RISK_OFF_CLOSE_ENABLED = original_value
            actions_module.RISK_OFF_CLOSE_ENABLED = original_value
    
    def test_risk_off_close_disabled_returns_alert(self):
        """Test that RISK_OFF with CLOSE_ENABLED=False returns ALERT (HIGH)."""
        position = Position(
            id="test-risk-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "regime": "RISK_OFF",
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ALERT
        assert decision.urgency == Urgency.HIGH
        assert "RISK_OFF" in decision.reasons[0]
        assert any("Reduce exposure" in step for step in decision.next_steps)
    
    def test_risk_off_ignored_for_closed_position(self):
        """Test that RISK_OFF does not trigger for CLOSED positions."""
        position = Position(
            id="test-risk-3",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        market_ctx = {
            "regime": "RISK_OFF",
        }
        
        decision = decide_position_action(position, market_ctx)
        
        # Should return HOLD (position not actionable), not ALERT/CLOSE
        assert decision.action == ActionType.HOLD
        assert decision.urgency == Urgency.LOW
    
    def test_panic_drawdown_threshold_hit(self):
        """Test that panic drawdown >= 10% returns ALERT (HIGH)."""
        position = Position(
            id="test-risk-4",
            symbol="AMZN",
            position_type="CSP",
            strike=100.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=200.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        entry_price = 100.0
        current_price = 89.0  # 11% drawdown (above 10% threshold)
        
        market_ctx = {
            "entry_underlying_price": entry_price,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ALERT
        assert decision.urgency == Urgency.HIGH
        assert any("Panic drawdown" in reason for reason in decision.reasons)
        assert any("defensive roll" in step.lower() for step in decision.next_steps)
    
    def test_panic_drawdown_below_threshold(self):
        """Test that drawdown < 10% does not trigger panic alert."""
        position = Position(
            id="test-risk-5",
            symbol="META",
            position_type="CSP",
            strike=250.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=350.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        entry_price = 250.0
        current_price = 226.0  # 9.6% drawdown (below 10% threshold)
        
        market_ctx = {
            "entry_underlying_price": entry_price,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        # Should not be ALERT due to drawdown (may be other action based on other rules)
        assert decision.action != ActionType.ALERT or not any("Panic drawdown" in r for r in decision.reasons)
    
    def test_panic_drawdown_exactly_at_threshold(self):
        """Test that drawdown exactly at 10% threshold triggers alert."""
        position = Position(
            id="test-risk-6",
            symbol="GOOGL",
            position_type="CSP",
            strike=120.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=250.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        entry_price = 100.0
        current_price = 90.0  # Exactly 10% drawdown
        
        market_ctx = {
            "entry_underlying_price": entry_price,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ALERT
        assert decision.urgency == Urgency.HIGH
        assert any("Panic drawdown" in reason for reason in decision.reasons)
    
    def test_panic_drawdown_missing_entry_price(self):
        """Test that missing entry_price does not trigger drawdown check."""
        position = Position(
            id="test-risk-7",
            symbol="TSLA",
            position_type="CSP",
            strike=180.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "underlying_price": 150.0,  # No entry_price
        }
        
        decision = decide_position_action(position, market_ctx)
        
        # Should not be ALERT due to drawdown (no entry price to compare)
        assert decision.action != ActionType.ALERT or not any("Panic drawdown" in r for r in decision.reasons)
    
    def test_ema200_break_detection(self):
        """Test that price below EMA200 break threshold returns ALERT (HIGH)."""
        position = Position(
            id="test-risk-8",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        ema200 = 400.0
        current_price = 390.0  # Below EMA200 * (1 - 0.02) = 392.0
        
        market_ctx = {
            "ema200": ema200,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ALERT
        assert decision.urgency == Urgency.HIGH
        assert any("EMA200 break" in reason for reason in decision.reasons)
    
    def test_ema200_break_at_threshold(self):
        """Test that price exactly at break threshold triggers alert."""
        position = Position(
            id="test-risk-9",
            symbol="QQQ",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        ema200 = 100.0
        break_threshold = ema200 * (1 - 0.02)  # 98.0
        current_price = 97.99  # Just below threshold
        
        market_ctx = {
            "ema200": ema200,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        assert decision.action == ActionType.ALERT
        assert decision.urgency == Urgency.HIGH
        assert any("EMA200 break" in reason for reason in decision.reasons)
    
    def test_ema200_break_above_threshold(self):
        """Test that price above break threshold does not trigger alert."""
        position = Position(
            id="test-risk-10",
            symbol="IWM",
            position_type="CSP",
            strike=180.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=300.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        ema200 = 100.0
        break_threshold = ema200 * (1 - 0.02)  # 98.0
        current_price = 98.01  # Just above threshold
        
        market_ctx = {
            "ema200": ema200,
            "underlying_price": current_price,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        # Should not be ALERT due to EMA200 break
        assert decision.action != ActionType.ALERT or not any("EMA200 break" in r for r in decision.reasons)
    
    def test_risk_overrides_priority_order(self):
        """Test that RISK_OFF takes priority over other rules."""
        position = Position(
            id="test-risk-11",
            symbol="DIA",
            position_type="CSP",
            strike=350.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=(350.0 * 100) * 0.70,  # 70% premium (would trigger CLOSE)
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        market_ctx = {
            "regime": "RISK_OFF",
            "premium_collected_pct": 70.0,
        }
        
        decision = decide_position_action(position, market_ctx)
        
        # RISK_OFF should take priority over premium capture rule
        assert decision.action == ActionType.ALERT  # CLOSE_ENABLED is False by default
        assert "RISK_OFF" in decision.reasons[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
