# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for daily plan message formatting."""

import pytest
from datetime import date, datetime, timedelta

from app.core.models.position import Position
from app.core.engine.actions import (
    ActionType,
    Urgency,
    ActionDecision,
    RollPlan,
)
from main import build_daily_plan_message


class TestDailyPlanMessageFormatting:
    """Test daily plan message formatting."""
    
    def test_basic_message_structure(self):
        """Test basic message structure with regime and candidates."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 85,
        }
        candidates = [
            {
                "symbol": "AAPL",
                "score": 90,
                "reasons": ["Uptrend above EMA200", "Pullback near EMA50"],
            },
            {
                "symbol": "MSFT",
                "score": 75,
                "reasons": ["RSI oversold"],
            },
        ]
        
        message = build_daily_plan_message(regime_result, candidates)
        
        assert "*ChakraOps Daily Plan*" in message
        assert "*Market Regime:* RISK_ON (Confidence: 85%)" in message
        assert "*Top CSP Candidates:*" in message
        assert "*AAPL* (Score: 90/100)" in message
        assert "*MSFT* (Score: 75/100)" in message
        assert "Uptrend above EMA200" in message
    
    def test_message_with_open_positions(self):
        """Test message includes open positions decisions."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 80,
        }
        candidates = []
        
        position1 = Position(
            id="test-1",
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
        
        decision1 = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required at this time"],
            next_steps=["Continue monitoring position"],
            computed_at=datetime.now(),
        )
        
        positions = [position1]
        decisions = [decision1]
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=positions,
            position_decisions=decisions,
        )
        
        assert "📌 *Open Positions Decisions*" in message
        assert "AAPL | OPEN | HOLD | LOW | No action required at this time" in message
    
    def test_message_with_high_urgency_action_alerts(self):
        """Test that HIGH urgency decisions appear in Action Alerts section."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 75,
        }
        candidates = []
        
        position1 = Position(
            id="test-2",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=5)).isoformat(),
            contracts=1,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        roll_plan = RollPlan(
            roll_type="defensive",
            suggested_expiry=date.today() + timedelta(days=35),
            suggested_strike=270.0,
            notes=["Defensive roll"],
        )
        
        decision1 = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
        
        position2 = Position(
            id="test-3",
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
        
        decision2 = ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["No action required"],
            next_steps=["Continue monitoring"],
            computed_at=datetime.now(),
        )
        
        positions = [position1, position2]
        decisions = [decision1, decision2]
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=positions,
            position_decisions=decisions,
        )
        
        assert "🔥 *Action Alerts*" in message
        assert "*NVDA* | OPEN | ROLL | HIGH | Expiry within 7 days" in message
        assert "→ Roll: 270 @" in message
        assert "defensive" in message
        # LOW urgency should not be in Action Alerts
        assert "AMZN" not in message.split("🔥 *Action Alerts*")[1].split("📌")[0]
    
    def test_message_with_roll_plan_details(self):
        """Test that ROLL actions include roll plan details."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 70,
        }
        candidates = []
        
        position = Position(
            id="test-4",
            symbol="META",
            position_type="CSP",
            strike=250.0,
            expiry=(date.today() + timedelta(days=6)).isoformat(),
            contracts=1,
            premium_collected=350.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        roll_plan = RollPlan(
            roll_type="out",
            suggested_expiry=date.today() + timedelta(days=40),
            suggested_strike=285.0,
            notes=["Out roll"],
        )
        
        decision = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
        
        positions = [position]
        decisions = [decision]
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=positions,
            position_decisions=decisions,
        )
        
        assert "META | OPEN | ROLL | HIGH" in message
        assert "→ Roll: 285 @" in message
        assert "out" in message
        # Check expiry date is in the message
        expiry_str = roll_plan.suggested_expiry.isoformat()
        assert expiry_str in message or str(roll_plan.suggested_expiry) in message
    
    def test_message_with_multiple_high_urgency_alerts(self):
        """Test message with multiple HIGH urgency alerts."""
        regime_result = {
            "regime": "RISK_OFF",
            "confidence": 90,
        }
        candidates = []
        
        position1 = Position(
            id="test-5",
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
        
        decision1 = ActionDecision(
            action=ActionType.ALERT,
            urgency=Urgency.HIGH,
            reasons=["RISK_OFF regime detected"],
            next_steps=["Reduce exposure"],
            computed_at=datetime.now(),
        )
        
        position2 = Position(
            id="test-6",
            symbol="TSLA",
            position_type="CSP",
            strike=180.0,
            expiry=(date.today() + timedelta(days=4)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        roll_plan = RollPlan(
            roll_type="defensive",
            suggested_expiry=date.today() + timedelta(days=35),
            suggested_strike=160.0,
            notes=["Defensive roll"],
        )
        
        decision2 = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
        
        positions = [position1, position2]
        decisions = [decision1, decision2]
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=positions,
            position_decisions=decisions,
        )
        
        assert "🔥 *Action Alerts*" in message
        assert "*GOOGL*" in message
        assert "*TSLA*" in message
        assert "ALERT" in message
        assert "ROLL" in message
        # Both should be in Action Alerts section
        alerts_section = message.split("🔥 *Action Alerts*")[1].split("📌")[0]
        assert "GOOGL" in alerts_section
        assert "TSLA" in alerts_section
    
    def test_message_with_no_positions(self):
        """Test message when there are no open positions."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 85,
        }
        candidates = [
            {
                "symbol": "AAPL",
                "score": 90,
                "reasons": ["Uptrend"],
            },
        ]
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=[],
            position_decisions=[],
        )
        
        assert "📌 *Open Positions Decisions*" in message
        assert "No open positions." in message
        assert "*Top CSP Candidates:*" in message
    
    def test_message_section_order(self):
        """Test that message sections appear in correct order."""
        regime_result = {
            "regime": "RISK_ON",
            "confidence": 80,
        }
        candidates = [{"symbol": "AAPL", "score": 90, "reasons": []}]
        
        position = Position(
            id="test-7",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=500.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        roll_plan = RollPlan(
            roll_type="out",
            suggested_expiry=date.today() + timedelta(days=35),
            suggested_strike=380.0,
            notes=["Out roll"],
        )
        
        decision = ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=["Consider rolling"],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
        
        message = build_daily_plan_message(
            regime_result,
            candidates,
            positions=[position],
            position_decisions=[decision],
        )
        
        # Check section order
        action_alerts_idx = message.find("🔥 *Action Alerts*")
        positions_idx = message.find("📌 *Open Positions Decisions*")
        candidates_idx = message.find("*Top CSP Candidates:*")
        
        assert action_alerts_idx != -1
        assert positions_idx != -1
        assert candidates_idx != -1
        assert action_alerts_idx < positions_idx < candidates_idx


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
