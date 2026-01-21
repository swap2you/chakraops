# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Execution Planner."""

import pytest
from datetime import datetime, timezone

from app.core.execution_planner import (
    ExecutionPlan,
    ExecutionPlanBlockedError,
    plan_execution,
)
from app.core.execution_guard import ExecutionIntent


class TestHoldAction:
    """Test HOLD action planning."""
    
    def test_hold_plan_creation(self):
        """Test that HOLD action creates a no-op plan."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="HOLD",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.symbol == "AAPL"
        assert plan.action == "HOLD"
        assert len(plan.steps) > 0
        assert "No execution required" in plan.steps[0]
        assert plan.parameters["execution_type"] == "NO_OP"
        assert plan.confidence == "HIGH"
        assert len(plan.risk_notes) > 0
    
    def test_hold_plan_has_correct_structure(self):
        """Test that HOLD plan has all required fields."""
        intent = ExecutionIntent(
            symbol="MSFT",
            action="HOLD",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert hasattr(plan, "symbol")
        assert hasattr(plan, "action")
        assert hasattr(plan, "steps")
        assert hasattr(plan, "parameters")
        assert hasattr(plan, "risk_notes")
        assert hasattr(plan, "confidence")
        assert hasattr(plan, "created_at")
        
        assert isinstance(plan.steps, list)
        assert isinstance(plan.parameters, dict)
        assert isinstance(plan.risk_notes, list)
        assert plan.confidence in ["HIGH", "MEDIUM", "LOW"]


class TestCloseAction:
    """Test CLOSE action planning."""
    
    def test_close_plan_creation(self):
        """Test that CLOSE action creates a buy-to-close plan."""
        intent = ExecutionIntent(
            symbol="SPY",
            action="CLOSE",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.symbol == "SPY"
        assert plan.action == "CLOSE"
        assert len(plan.steps) >= 5
        assert "buy-to-close" in plan.steps[2].lower()
        assert plan.parameters["execution_type"] == "BUY_TO_CLOSE"
        assert plan.parameters["pricing_strategy"] == "LIMIT_AT_MID"
        assert plan.parameters["limit_price_offset"] == 0.05
        assert plan.confidence == "HIGH"
        assert len(plan.risk_notes) > 0
    
    def test_close_plan_has_pricing_parameters(self):
        """Test that CLOSE plan includes pricing parameters."""
        intent = ExecutionIntent(
            symbol="NVDA",
            action="CLOSE",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="MEDIUM",
        )
        
        plan = plan_execution(intent)
        
        assert "pricing_strategy" in plan.parameters
        assert "limit_price_offset" in plan.parameters
        assert "order_type" in plan.parameters
        assert "time_in_force" in plan.parameters
        assert plan.parameters["order_type"] == "LIMIT"
        assert plan.parameters["time_in_force"] == "DAY"


class TestRollAction:
    """Test ROLL action planning."""
    
    def test_roll_plan_creation(self):
        """Test that ROLL action creates a two-leg plan."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="ROLL",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.symbol == "AAPL"
        assert plan.action == "ROLL"
        assert len(plan.steps) >= 10
        assert "buy-to-close" in plan.steps[1].lower()
        # Check that sell-to-open appears in any step (it's in step 4)
        assert any("sell-to-open" in step.lower() for step in plan.steps)
        assert plan.parameters["execution_type"] == "ROLL"
        assert plan.parameters["leg1_type"] == "BUY_TO_CLOSE"
        assert plan.parameters["leg2_type"] == "SELL_TO_OPEN"
        assert plan.confidence == "HIGH"
        assert len(plan.risk_notes) > 0
    
    def test_roll_plan_has_both_leg_parameters(self):
        """Test that ROLL plan includes parameters for both legs."""
        intent = ExecutionIntent(
            symbol="MSFT",
            action="ROLL",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="MEDIUM",
        )
        
        plan = plan_execution(intent)
        
        assert "leg1_type" in plan.parameters
        assert "leg1_pricing_strategy" in plan.parameters
        assert "leg1_limit_price_offset" in plan.parameters
        assert "leg2_type" in plan.parameters
        assert "leg2_pricing_strategy" in plan.parameters
        assert "leg2_limit_price_offset" in plan.parameters
        assert plan.parameters["leg1_limit_price_offset"] == 0.05
        assert plan.parameters["leg2_limit_price_offset"] == -0.05
        assert plan.parameters["roll_net_credit_target"] == "POSITIVE"


class TestAlertAction:
    """Test ALERT action planning."""
    
    def test_alert_plan_creation(self):
        """Test that ALERT action creates a notification-only plan."""
        intent = ExecutionIntent(
            symbol="SPY",
            action="ALERT",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.symbol == "SPY"
        assert plan.action == "ALERT"
        assert len(plan.steps) >= 4
        assert "notification" in plan.steps[0].lower()
        assert plan.parameters["execution_type"] == "NOTIFICATION_ONLY"
        assert "notification_channels" in plan.parameters
        assert plan.confidence == "HIGH"
        assert len(plan.risk_notes) > 0
    
    def test_alert_plan_has_notification_channels(self):
        """Test that ALERT plan includes notification channels."""
        intent = ExecutionIntent(
            symbol="NVDA",
            action="ALERT",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert isinstance(plan.parameters["notification_channels"], list)
        assert "DATABASE" in plan.parameters["notification_channels"]
        assert "SLACK" in plan.parameters["notification_channels"]


class TestBlockedExecution:
    """Test blocked execution scenarios."""
    
    def test_blocked_intent_raises_error(self):
        """Test that blocked intent raises ExecutionPlanBlockedError."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="CLOSE",
            approved=False,
            blocked_reason="State machine does not allow CLOSE from CLOSED",
            risk_flags=["STATE_MACHINE_BLOCKED"],
            confidence="HIGH",
        )
        
        with pytest.raises(ExecutionPlanBlockedError) as exc_info:
            plan_execution(intent)
        
        assert exc_info.value.symbol == "AAPL"
        assert exc_info.value.action == "CLOSE"
        assert "CLOSED" in exc_info.value.blocked_reason or exc_info.value.blocked_reason is not None
    
    def test_blocked_roll_raises_error(self):
        """Test that blocked ROLL raises ExecutionPlanBlockedError."""
        intent = ExecutionIntent(
            symbol="MSFT",
            action="ROLL",
            approved=False,
            blocked_reason="Market regime is RISK_OFF",
            risk_flags=["REGIME_BLOCKED"],
            confidence="HIGH",
        )
        
        with pytest.raises(ExecutionPlanBlockedError) as exc_info:
            plan_execution(intent)
        
        assert exc_info.value.symbol == "MSFT"
        assert exc_info.value.action == "ROLL"
        assert "RISK_OFF" in exc_info.value.blocked_reason or exc_info.value.blocked_reason is not None
    
    def test_blocked_close_raises_error(self):
        """Test that blocked CLOSE raises ExecutionPlanBlockedError."""
        intent = ExecutionIntent(
            symbol="SPY",
            action="CLOSE",
            approved=False,
            blocked_reason="CLOSE action has LOW urgency/confidence",
            risk_flags=["CONFIDENCE_BLOCKED"],
            confidence="MEDIUM",
        )
        
        with pytest.raises(ExecutionPlanBlockedError) as exc_info:
            plan_execution(intent)
        
        assert exc_info.value.symbol == "SPY"
        assert exc_info.value.action == "CLOSE"


class TestInvalidInputs:
    """Test handling of invalid inputs."""
    
    def test_none_intent_raises_value_error(self):
        """Test that None intent raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            plan_execution(None)  # type: ignore
        
        assert "None" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()
    
    def test_unknown_action_type(self):
        """Test that unknown action type creates plan with warning."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="UNKNOWN_ACTION",
            approved=True,
            risk_flags=[],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.symbol == "AAPL"
        assert plan.action == "UNKNOWN_ACTION"
        assert len(plan.risk_notes) > 0
        assert "Unknown action type" in plan.risk_notes[0]
        assert plan.confidence == "LOW"


class TestExecutionPlanStructure:
    """Test ExecutionPlan dataclass structure."""
    
    def test_execution_plan_has_all_fields(self):
        """Test that ExecutionPlan has all required fields."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="HOLD",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert hasattr(plan, "symbol")
        assert hasattr(plan, "action")
        assert hasattr(plan, "steps")
        assert hasattr(plan, "parameters")
        assert hasattr(plan, "risk_notes")
        assert hasattr(plan, "confidence")
        assert hasattr(plan, "created_at")
        
        assert plan.symbol == "AAPL"
        assert plan.action == "HOLD"
        assert isinstance(plan.steps, list)
        assert isinstance(plan.parameters, dict)
        assert isinstance(plan.risk_notes, list)
        assert plan.confidence in ["HIGH", "MEDIUM", "LOW"]
        assert isinstance(plan.created_at, str)
    
    def test_created_at_is_iso_format(self):
        """Test that created_at is in ISO format."""
        intent = ExecutionIntent(
            symbol="MSFT",
            action="HOLD",
            approved=True,
            risk_flags=["NO_EXECUTION_REQUIRED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        # Should be parseable as ISO datetime
        try:
            datetime.fromisoformat(plan.created_at.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"created_at is not valid ISO format: {plan.created_at}")


class TestConfidencePropagation:
    """Test that confidence is propagated correctly."""
    
    def test_high_confidence_propagated(self):
        """Test that HIGH confidence from intent is propagated to plan."""
        intent = ExecutionIntent(
            symbol="AAPL",
            action="CLOSE",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="HIGH",
        )
        
        plan = plan_execution(intent)
        
        assert plan.confidence == "HIGH"
    
    def test_medium_confidence_propagated(self):
        """Test that MEDIUM confidence from intent is propagated to plan."""
        intent = ExecutionIntent(
            symbol="MSFT",
            action="ROLL",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="MEDIUM",
        )
        
        plan = plan_execution(intent)
        
        assert plan.confidence == "MEDIUM"
    
    def test_low_confidence_propagated(self):
        """Test that LOW confidence from intent is propagated to plan."""
        intent = ExecutionIntent(
            symbol="SPY",
            action="CLOSE",
            approved=True,
            risk_flags=["STATE_MACHINE_VALIDATED"],
            confidence="LOW",
        )
        
        plan = plan_execution(intent)
        
        assert plan.confidence == "LOW"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
