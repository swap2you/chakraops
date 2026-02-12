# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Execution Guard with System Health integration."""

import pytest
from datetime import date, datetime, timedelta

from app.core.execution_guard import ExecutionIntent, evaluate_execution
from app.core.action_engine import ActionDecision
from app.core.models.position import Position
from app.core.system_health import SystemHealthSnapshot


class TestSystemHealthHalt:
    """Test that SYSTEM_HALTED blocks all executions."""
    
    def test_halt_blocks_close_action(self):
        """Test that HALT status blocks CLOSE action."""
        position = Position(
            id="test-1",
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
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["PREMIUM_70_PCT"],
            explanation="Premium >= 70%",
            allowed_next_states=["CLOSING"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=5,
            actionable_candidates=3,
            blocked_actions=0,
            error_count_24h=0,
            warning_count_24h=0,
            health_score=30,  # Below 50 = HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.blocked_reason
        assert "SYSTEM_HALTED" in intent.risk_flags
        assert intent.confidence == "HIGH"
    
    def test_halt_blocks_roll_action(self):
        """Test that HALT status blocks ROLL action."""
        position = Position(
            id="test-2",
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
        
        system_health = SystemHealthSnapshot(
            regime="RISK_OFF",
            regime_confidence=65,
            total_candidates=0,
            actionable_candidates=0,
            blocked_actions=5,
            error_count_24h=3,
            warning_count_24h=0,
            health_score=40,  # Below 50 = HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_OFF",
            system_health=system_health,
        )
        
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.blocked_reason
        assert "SYSTEM_HALTED" in intent.risk_flags
    
    def test_halt_blocks_open_action(self):
        """Test that HALT status blocks OPEN action."""
        position = Position(
            id="test-3",
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
        
        system_health = SystemHealthSnapshot(
            regime="RISK_OFF",
            regime_confidence=60,
            total_candidates=0,
            actionable_candidates=0,
            blocked_actions=0,
            error_count_24h=5,
            warning_count_24h=0,
            health_score=25,  # Below 50 = HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_OFF",
            system_health=system_health,
        )
        
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.blocked_reason
        assert "SYSTEM_HALTED" in intent.risk_flags
    
    def test_halt_blocks_even_hold_action(self):
        """Test that HALT status blocks even HOLD action (though HOLD normally requires no execution)."""
        position = Position(
            id="test-4",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry=(date.today() + timedelta(days=30)).isoformat(),
            contracts=1,
            premium_collected=450.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="NVDA",
            action="HOLD",
            urgency="LOW",
            reason_codes=["DEFAULT"],
            explanation="No action required",
            allowed_next_states=["OPEN"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=50,
            total_candidates=0,
            actionable_candidates=0,
            blocked_actions=0,
            error_count_24h=10,
            warning_count_24h=0,
            health_score=0,  # HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.blocked_reason
        assert "SYSTEM_HALTED" in intent.risk_flags


class TestSystemHealthDegraded:
    """Test that SYSTEM_DEGRADED allows execution but adds flag."""
    
    def test_degraded_allows_close_with_flag(self):
        """Test that DEGRADED status allows CLOSE but adds flag."""
        position = Position(
            id="test-5",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry=(date.today() + timedelta(days=3)).isoformat(),
            contracts=1,
            premium_collected=800.0,
            entry_date=datetime.now().isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        action_decision = ActionDecision(
            symbol="AAPL",
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["DTE_LE_3", "PREMIUM_50_PCT"],
            explanation="DTE <= 3 and premium >= 50%",
            allowed_next_states=["CLOSING"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=65,
            total_candidates=5,
            actionable_candidates=2,
            blocked_actions=3,
            error_count_24h=0,
            warning_count_24h=0,
            health_score=70,  # 50-79 = DEGRADED
            status="DEGRADED",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        assert intent.approved is True  # Should still be approved
        assert "SYSTEM_DEGRADED" in intent.risk_flags
        assert intent.blocked_reason is None
    
    def test_degraded_allows_roll_with_flag(self):
        """Test that DEGRADED status allows ROLL but adds flag."""
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
            reason_codes=["DTE_LE_7", "PREMIUM_LT_50", "PRICE_GT_EMA50"],
            explanation="DTE <= 7, premium < 50%, price > EMA50",
            allowed_next_states=["ROLLING"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=60,
            total_candidates=3,
            actionable_candidates=1,
            blocked_actions=2,
            error_count_24h=1,
            warning_count_24h=0,
            health_score=60,  # 50-79 = DEGRADED
            status="DEGRADED",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        assert intent.approved is True
        assert "SYSTEM_DEGRADED" in intent.risk_flags
        # Should also have STATE_MACHINE_VALIDATED if transition is valid
        assert intent.blocked_reason is None


class TestSystemHealthHealthy:
    """Test that HEALTHY status allows normal execution."""
    
    def test_healthy_allows_execution_no_flag(self):
        """Test that HEALTHY status allows execution without special flag."""
        position = Position(
            id="test-7",
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
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
            health_score=100,  # >= 80 = HEALTHY
            status="HEALTHY",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        assert intent.approved is True
        assert "SYSTEM_DEGRADED" not in intent.risk_flags
        assert "SYSTEM_HALTED" not in intent.risk_flags
        assert intent.blocked_reason is None
    
    def test_healthy_behavior_unchanged(self):
        """Test that HEALTHY status does not change existing behavior."""
        position = Position(
            id="test-8",
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
            urgency="LOW",  # Should be blocked by confidence rule
            reason_codes=["DEFAULT"],
            explanation="Low confidence close",
            allowed_next_states=["CLOSING"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=2,
            error_count_24h=0,
            warning_count_24h=0,
            health_score=100,
            status="HEALTHY",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        # Should still be blocked by confidence rule (not by system health)
        assert intent.approved is False
        assert "CONFIDENCE_BLOCKED" in intent.risk_flags
        assert "SYSTEM_HALTED" not in intent.risk_flags
        assert "SYSTEM_DEGRADED" not in intent.risk_flags


class TestSystemHealthNone:
    """Test that None system_health does not affect execution."""
    
    def test_none_system_health_allows_execution(self):
        """Test that None system_health allows normal execution."""
        position = Position(
            id="test-9",
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
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["PREMIUM_70_PCT"],
            explanation="Premium >= 70%",
            allowed_next_states=["CLOSING"],
        )
        
        # No system_health provided
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=None,
        )
        
        assert intent.approved is True
        assert "SYSTEM_HALTED" not in intent.risk_flags
        assert "SYSTEM_DEGRADED" not in intent.risk_flags


class TestSystemHealthPriority:
    """Test that system health HALT takes priority over other rules."""
    
    def test_halt_overrides_confidence_blocking(self):
        """Test that HALT overrides confidence blocking."""
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
            action="CLOSE",
            urgency="LOW",  # Would normally be blocked by confidence
            reason_codes=["DEFAULT"],
            explanation="Low confidence close",
            allowed_next_states=["CLOSING"],
        )
        
        system_health = SystemHealthSnapshot(
            regime="RISK_ON",
            regime_confidence=85,
            total_candidates=10,
            actionable_candidates=5,
            blocked_actions=0,
            error_count_24h=10,
            warning_count_24h=0,
            health_score=0,  # HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_ON",
            system_health=system_health,
        )
        
        # Should be blocked by HALT, not by confidence
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.risk_flags
        assert "SYSTEM_HALTED" in intent.blocked_reason
        # Should NOT have CONFIDENCE_BLOCKED because HALT takes priority
        assert "CONFIDENCE_BLOCKED" not in intent.risk_flags
    
    def test_halt_overrides_regime_blocking(self):
        """Test that HALT overrides regime blocking."""
        position = Position(
            id="test-11",
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
        
        system_health = SystemHealthSnapshot(
            regime="RISK_OFF",
            regime_confidence=60,
            total_candidates=0,
            actionable_candidates=0,
            blocked_actions=0,
            error_count_24h=10,
            warning_count_24h=0,
            health_score=0,  # HALT
            status="HALT",
        )
        
        intent = evaluate_execution(
            action_decision,
            position,
            "RISK_OFF",  # Would normally be blocked by regime
            system_health=system_health,
        )
        
        # Should be blocked by HALT, not by regime
        assert intent.approved is False
        assert "SYSTEM_HALTED" in intent.risk_flags
        assert "SYSTEM_HALTED" in intent.blocked_reason
        # Should NOT have REGIME_BLOCKED because HALT takes priority
        assert "REGIME_BLOCKED" not in intent.risk_flags


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
