# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Execution Guardrails."""

import pytest
from datetime import date, datetime, timedelta, timezone

from app.core.execution_guard import (
    ExecutionIntent,
    evaluate_execution,
    DEFAULT_TTL_MINUTES,
)
from app.core.action_engine import ActionDecision
from app.core.models.position import Position
from app.core.system_health import SystemHealthSnapshot


class TestApproval:
    """Test execution approval scenarios."""
    
    def test_hold_action_always_approved(self):
        """Test that HOLD actions are always approved."""
        position = Position(
            id="test-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is True
        assert intent.blocked_reason is None
        assert "NO_EXECUTION_REQUIRED" in intent.risk_flags
        assert intent.confidence == "HIGH"
    
    def test_alert_action_always_approved(self):
        """Test that ALERT actions are always approved."""
        position = Position(
            id="test-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=600.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="MSFT",
            action="ALERT",
            urgency="HIGH",
            reason_codes=["PRICE_LT_EMA200"],
            explanation="Price below EMA200",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is True
        assert intent.blocked_reason is None
        assert "NO_EXECUTION_REQUIRED" in intent.risk_flags
        assert intent.confidence == "HIGH"
    
    def test_close_action_approved_when_high_urgency(self):
        """Test that CLOSE actions are approved when urgency is HIGH."""
        position = Position(
            id="test-3",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=800.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="SPY",
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["DTE_LE_3", "PREMIUM_50_PCT"],
            explanation="DTE <= 3 and premium >= 50%",
            allowed_next_states=["CLOSING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is True
        assert intent.blocked_reason is None
        assert "STATE_MACHINE_VALIDATED" in intent.risk_flags
        assert intent.confidence == "HIGH"
    
    def test_roll_action_approved_in_risk_on(self):
        """Test that ROLL actions are approved in RISK_ON regime."""
        position = Position(
            id="test-4",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="NVDA",
            action="ROLL",
            urgency="HIGH",
            reason_codes=["DTE_LE_7", "PREMIUM_LT_50", "PRICE_GT_EMA50"],
            explanation="DTE <= 7, premium < 50%, price > EMA50",
            allowed_next_states=["ROLLING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is True
        assert intent.blocked_reason is None
        assert "STATE_MACHINE_VALIDATED" in intent.risk_flags
        assert intent.confidence == "HIGH"


class TestBlocking:
    """Test execution blocking scenarios."""
    
    def test_close_blocked_when_low_urgency(self):
        """Test that CLOSE actions are blocked when urgency is LOW."""
        position = Position(
            id="test-5",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="CLOSE",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="Low confidence close",
            allowed_next_states=["CLOSING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is False
        assert "CONFIDENCE_BLOCKED" in intent.risk_flags
        assert "CLOSE action has LOW urgency/confidence" in intent.blocked_reason
        assert intent.confidence == "MEDIUM"
    
    def test_roll_blocked_in_risk_off(self):
        """Test that ROLL actions are blocked when regime is RISK_OFF."""
        position = Position(
            id="test-6",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="MSFT",
            action="ROLL",
            urgency="HIGH",
            reason_codes=["DTE_LE_7"],
            explanation="DTE <= 7",
            allowed_next_states=["ROLLING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_OFF")
        
        assert intent.approved is False
        assert "REGIME_BLOCKED" in intent.risk_flags
        assert "RISK_OFF" in intent.blocked_reason
        assert intent.confidence == "HIGH"
    
    def test_open_blocked_in_risk_off(self):
        """Test that OPEN actions are blocked when regime is RISK_OFF."""
        # Use ASSIGNED state so state machine allows OPEN transition
        position = Position(
            id="test-7",
            symbol="SPY",
            position_type="CSP",
            strike=400.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=600.0,
            entry_date=datetime.now().isoformat(),
            status="ASSIGNED",
            state="ASSIGNED",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="SPY",
            action="OPEN",
            urgency="HIGH",
            reason_codes=["NEW_POSITION"],
            explanation="New position",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_OFF")
        
        assert intent.approved is False
        assert "REGIME_BLOCKED" in intent.risk_flags
        assert "RISK_OFF" in intent.blocked_reason
        assert intent.confidence == "HIGH"


class TestStateMachineBlocking:
    """Test state machine validation blocking."""
    
    def test_close_blocked_from_closed_state(self):
        """Test that CLOSE is blocked from CLOSED state."""
        position = Position(
            id="test-8",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["PREMIUM_70_PCT"],
            explanation="Premium >= 70%",
            allowed_next_states=["CLOSING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is False
        assert "STATE_MACHINE_BLOCKED" in intent.risk_flags
        assert "does not allow" in intent.blocked_reason
        assert intent.confidence == "HIGH"
    
    def test_roll_blocked_from_closed_state(self):
        """Test that ROLL is blocked from CLOSED state."""
        position = Position(
            id="test-9",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="MSFT",
            action="ROLL",
            urgency="HIGH",
            reason_codes=["DTE_LE_7"],
            explanation="DTE <= 7",
            allowed_next_states=["ROLLING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is False
        assert "STATE_MACHINE_BLOCKED" in intent.risk_flags
        assert "does not allow" in intent.blocked_reason


class TestTTL:
    """Test TTL (time-to-live) enforcement."""
    
    def test_default_ttl_is_15_minutes(self):
        """Test that default TTL is 15 minutes."""
        position = Position(
            id="test-10",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        # Parse timestamps
        computed_at = datetime.fromisoformat(intent.computed_at.replace('Z', '+00:00'))
        expires_at = datetime.fromisoformat(intent.expires_at.replace('Z', '+00:00'))
        
        # Check TTL is approximately 15 minutes
        ttl_delta = expires_at - computed_at
        assert abs(ttl_delta.total_seconds() - (DEFAULT_TTL_MINUTES * 60)) < 5  # Allow 5 second tolerance
    
    def test_custom_ttl(self):
        """Test that custom TTL is respected."""
        position = Position(
            id="test-11",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=600.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="MSFT",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        custom_ttl = 30  # 30 minutes
        intent = evaluate_execution(action_decision, position, "RISK_ON", ttl_minutes=custom_ttl)
        
        # Parse timestamps
        computed_at = datetime.fromisoformat(intent.computed_at.replace('Z', '+00:00'))
        expires_at = datetime.fromisoformat(intent.expires_at.replace('Z', '+00:00'))
        
        # Check TTL is approximately 30 minutes
        ttl_delta = expires_at - computed_at
        assert abs(ttl_delta.total_seconds() - (custom_ttl * 60)) < 5  # Allow 5 second tolerance


class TestInvalidInputs:
    """Test handling of invalid inputs."""
    
    def test_none_action_decision(self):
        """Test that None action_decision is handled."""
        position = Position(
            id="test-12",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        intent = evaluate_execution(None, position, "RISK_ON")  # type: ignore
        
        assert intent.approved is False
        assert "INVALID_INPUT" in intent.risk_flags
        assert intent.blocked_reason is not None
        assert "None" in intent.blocked_reason or "invalid" in intent.blocked_reason.lower()
        assert intent.confidence == "LOW"
    
    def test_none_position(self):
        """Test that None position is handled."""
        action_decision = ActionDecision(
            symbol="AAPL",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, None, "RISK_ON")  # type: ignore
        
        assert intent.approved is False
        assert "INVALID_INPUT" in intent.risk_flags
        assert intent.blocked_reason is not None
        assert "None" in intent.blocked_reason or "invalid" in intent.blocked_reason.lower()
        assert intent.confidence == "LOW"


class TestExecutionIntentStructure:
    """Test ExecutionIntent dataclass structure."""
    
    def test_execution_intent_has_all_fields(self):
        """Test that ExecutionIntent has all required fields."""
        position = Position(
            id="test-13",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert hasattr(intent, "symbol")
        assert hasattr(intent, "action")
        assert hasattr(intent, "approved")
        assert hasattr(intent, "blocked_reason")
        assert hasattr(intent, "risk_flags")
        assert hasattr(intent, "confidence")
        assert hasattr(intent, "computed_at")
        assert hasattr(intent, "expires_at")
        
        assert intent.symbol == "AAPL"
        assert intent.action == "HOLD"
        assert isinstance(intent.approved, bool)
        assert isinstance(intent.risk_flags, list)
        assert intent.confidence in ["HIGH", "MEDIUM", "LOW"]
        assert isinstance(intent.computed_at, str)
        assert isinstance(intent.expires_at, str)


class TestCombinedRules:
    """Test combinations of blocking rules."""
    
    def test_close_blocked_by_both_confidence_and_state_machine(self):
        """Test that CLOSE can be blocked by multiple rules."""
        position = Position(
            id="test-14",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="CLOSE",
            urgency="LOW",  # Low urgency triggers confidence blocking
            reason_codes=["DEFAULT"],
            explanation="Low confidence close",
            allowed_next_states=["CLOSING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_ON")
        
        assert intent.approved is False
        # Should be blocked by state machine (first check)
        assert "STATE_MACHINE_BLOCKED" in intent.risk_flags
        assert intent.confidence == "HIGH"
    
    def test_roll_blocked_by_both_regime_and_state_machine(self):
        """Test that ROLL can be blocked by multiple rules."""
        position = Position(
            id="test-15",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry=(date.today() + timedelta(days=7)).isoformat(),
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now().isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="MSFT",
            action="ROLL",
            urgency="HIGH",
            reason_codes=["DTE_LE_7"],
            explanation="DTE <= 7",
            allowed_next_states=["ROLLING"],
        )
        
        intent = evaluate_execution(action_decision, position, "RISK_OFF")
        
        assert intent.approved is False
        # Should be blocked by state machine first (CLOSED -> ROLL not allowed)
        assert "STATE_MACHINE_BLOCKED" in intent.risk_flags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
