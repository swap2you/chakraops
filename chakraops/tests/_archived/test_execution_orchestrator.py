# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Execution Orchestrator."""

import pytest
from datetime import datetime, timezone

from app.core.execution_orchestrator import (
    ExecutionResult,
    ExecutionOrchestrationError,
    orchestrate_execution,
)
from app.core.execution_planner import ExecutionPlan


class TestHoldAction:
    """Test HOLD action orchestration."""
    
    def test_hold_orchestration_creates_no_op_result(self):
        """Test that HOLD action creates NO_OP result."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="HOLD",
            steps=["No execution required", "Continue monitoring position"],
            parameters={"execution_type": "NO_OP"},
            risk_notes=["HOLD action requires no execution"],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "AAPL"
        assert result.action == "HOLD"
        assert result.status == "NO_OP"
        assert len(result.executed_steps) == 2
        assert "[SIMULATED]" in result.executed_steps[0]
        assert len(result.notes) > 0
        assert "no execution" in result.notes[0].lower()
    
    def test_hold_orchestration_has_correct_structure(self):
        """Test that HOLD result has all required fields."""
        plan = ExecutionPlan(
            symbol="MSFT",
            action="HOLD",
            steps=["No execution required"],
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert hasattr(result, "symbol")
        assert hasattr(result, "action")
        assert hasattr(result, "status")
        assert hasattr(result, "executed_steps")
        assert hasattr(result, "skipped_steps")
        assert hasattr(result, "notes")
        assert hasattr(result, "simulated_at")
        
        assert isinstance(result.executed_steps, list)
        assert isinstance(result.skipped_steps, list)
        assert isinstance(result.notes, list)
        assert result.status in ["SIMULATED", "NO_OP", "ERROR"]


class TestCloseAction:
    """Test CLOSE action orchestration."""
    
    def test_close_orchestration_creates_simulated_result(self):
        """Test that CLOSE action creates SIMULATED result."""
        plan = ExecutionPlan(
            symbol="SPY",
            action="CLOSE",
            steps=[
                "1. Calculate current option price (MID = (bid + ask) / 2)",
                "2. Set limit price at MID or slightly above (MID + 0.05)",
                "3. Place buy-to-close order",
            ],
            parameters={
                "execution_type": "BUY_TO_CLOSE",
                "pricing_strategy": "LIMIT_AT_MID",
                "limit_price_offset": 0.05,
            },
            risk_notes=["Buy-to-close order may not fill"],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "SPY"
        assert result.action == "CLOSE"
        assert result.status == "SIMULATED"
        assert len(result.executed_steps) == 3
        assert all("[SIMULATED]" in step for step in result.executed_steps)
        assert len(result.notes) > 0
        assert "DRY-RUN" in result.notes[0]
    
    def test_close_orchestration_includes_pricing_notes(self):
        """Test that CLOSE result includes pricing strategy notes."""
        plan = ExecutionPlan(
            symbol="NVDA",
            action="CLOSE",
            steps=["1. Calculate current option price"],
            parameters={
                "pricing_strategy": "LIMIT_AT_MID",
                "limit_price_offset": 0.05,
            },
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        # Check that pricing strategy is in notes
        notes_str = " ".join(result.notes)
        assert "pricing strategy" in notes_str.lower() or "LIMIT_AT_MID" in notes_str
        assert "$0.05" in notes_str or "0.05" in notes_str


class TestRollAction:
    """Test ROLL action orchestration."""
    
    def test_roll_orchestration_creates_simulated_result(self):
        """Test that ROLL action creates SIMULATED result."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="ROLL",
            steps=[
                "1. Calculate current option price",
                "2. Set buy-to-close limit price",
                "3. Place buy-to-close order",
                "4. After fill, place sell-to-open order",
            ],
            parameters={
                "execution_type": "ROLL",
                "leg1_type": "BUY_TO_CLOSE",
                "leg2_type": "SELL_TO_OPEN",
                "roll_net_credit_target": "POSITIVE",
            },
            risk_notes=["Roll requires two-leg execution"],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "AAPL"
        assert result.action == "ROLL"
        assert result.status == "SIMULATED"
        assert len(result.executed_steps) == 4
        assert all("[SIMULATED]" in step for step in result.executed_steps)
        assert len(result.notes) > 0
        assert "DRY-RUN" in result.notes[0]
        assert "two-leg" in result.notes[1].lower()
    
    def test_roll_orchestration_includes_leg_parameters(self):
        """Test that ROLL result includes leg parameters in notes."""
        plan = ExecutionPlan(
            symbol="MSFT",
            action="ROLL",
            steps=["1. Calculate current option price"],
            parameters={
                "leg1_type": "BUY_TO_CLOSE",
                "leg2_type": "SELL_TO_OPEN",
                "roll_net_credit_target": "POSITIVE",
            },
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        # Check that leg types are in notes
        notes_str = " ".join(result.notes)
        assert "BUY_TO_CLOSE" in notes_str or "buy-to-close" in notes_str.lower()
        assert "SELL_TO_OPEN" in notes_str or "sell-to-open" in notes_str.lower()
        assert "POSITIVE" in notes_str or "positive" in notes_str.lower()


class TestAlertAction:
    """Test ALERT action orchestration."""
    
    def test_alert_orchestration_creates_no_op_result(self):
        """Test that ALERT action creates NO_OP result."""
        plan = ExecutionPlan(
            symbol="SPY",
            action="ALERT",
            steps=[
                "1. Generate alert notification",
                "2. Log alert to database",
            ],
            parameters={"execution_type": "NOTIFICATION_ONLY"},
            risk_notes=["ALERT action requires no position execution"],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "SPY"
        assert result.action == "ALERT"
        assert result.status == "NO_OP"
        assert len(result.executed_steps) == 2
        assert all("[SIMULATED]" in step for step in result.executed_steps)
        assert len(result.notes) > 0
        assert "no position execution" in result.notes[0].lower() or "notification" in result.notes[0].lower()


class TestInvalidInputs:
    """Test handling of invalid inputs."""
    
    def test_none_plan_raises_error(self):
        """Test that None plan raises ExecutionOrchestrationError."""
        with pytest.raises(ExecutionOrchestrationError) as exc_info:
            orchestrate_execution(None)  # type: ignore
        
        assert "None" in str(exc_info.value) or "invalid" in str(exc_info.value).lower()
    
    def test_unknown_action_type_creates_error_result(self):
        """Test that unknown action type creates ERROR result."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="UNKNOWN_ACTION",
            steps=[],
            parameters={},
            risk_notes=[],
            confidence="LOW",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "AAPL"
        assert result.action == "UNKNOWN_ACTION"
        assert result.status == "ERROR"
        assert len(result.notes) > 0
        assert "Unknown action type" in result.notes[0]


class TestExecutionResultStructure:
    """Test ExecutionResult dataclass structure."""
    
    def test_execution_result_has_all_fields(self):
        """Test that ExecutionResult has all required fields."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="HOLD",
            steps=["No execution required"],
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert hasattr(result, "symbol")
        assert hasattr(result, "action")
        assert hasattr(result, "status")
        assert hasattr(result, "executed_steps")
        assert hasattr(result, "skipped_steps")
        assert hasattr(result, "notes")
        assert hasattr(result, "simulated_at")
        
        assert result.symbol == "AAPL"
        assert result.action == "HOLD"
        assert isinstance(result.executed_steps, list)
        assert isinstance(result.skipped_steps, list)
        assert isinstance(result.notes, list)
        assert result.status in ["SIMULATED", "NO_OP", "ERROR"]
        assert isinstance(result.simulated_at, str)
    
    def test_simulated_at_is_iso_format(self):
        """Test that simulated_at is in ISO format."""
        plan = ExecutionPlan(
            symbol="MSFT",
            action="HOLD",
            steps=["No execution required"],
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        # Should be parseable as ISO datetime
        try:
            datetime.fromisoformat(result.simulated_at.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"simulated_at is not valid ISO format: {result.simulated_at}")


class TestDeterministicOutput:
    """Test that orchestration produces deterministic output."""
    
    def test_same_plan_produces_same_result_structure(self):
        """Test that same plan produces same result structure."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="CLOSE",
            steps=[
                "1. Calculate current option price",
                "2. Place buy-to-close order",
            ],
            parameters={"pricing_strategy": "LIMIT_AT_MID"},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result1 = orchestrate_execution(plan)
        result2 = orchestrate_execution(plan)
        
        # Results should have same structure (timestamps may differ)
        assert result1.symbol == result2.symbol
        assert result1.action == result2.action
        assert result1.status == result2.status
        assert len(result1.executed_steps) == len(result2.executed_steps)
        assert len(result1.notes) == len(result2.notes)
        # Check that steps are identical (excluding timestamps)
        for step1, step2 in zip(result1.executed_steps, result2.executed_steps):
            assert step1 == step2
    
    def test_empty_steps_handled_gracefully(self):
        """Test that empty steps list is handled gracefully."""
        plan = ExecutionPlan(
            symbol="SPY",
            action="HOLD",
            steps=[],  # Empty steps
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert result.symbol == "SPY"
        assert result.action == "HOLD"
        assert result.status == "NO_OP"
        assert len(result.executed_steps) == 0
        assert len(result.notes) > 0


class TestStepSimulation:
    """Test that steps are properly simulated."""
    
    def test_all_steps_are_simulated(self):
        """Test that all steps in plan are simulated."""
        plan = ExecutionPlan(
            symbol="NVDA",
            action="ROLL",
            steps=[
                "1. Step one",
                "2. Step two",
                "3. Step three",
            ],
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert len(result.executed_steps) == 3
        assert all("[SIMULATED]" in step for step in result.executed_steps)
        assert all("Step" in step for step in result.executed_steps)
    
    def test_no_steps_are_skipped(self):
        """Test that no steps are skipped in normal execution."""
        plan = ExecutionPlan(
            symbol="AAPL",
            action="CLOSE",
            steps=[
                "1. Calculate price",
                "2. Place order",
            ],
            parameters={},
            risk_notes=[],
            confidence="HIGH",
        )
        
        result = orchestrate_execution(plan)
        
        assert len(result.executed_steps) == 2
        assert len(result.skipped_steps) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
