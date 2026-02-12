# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Operator UX – "What Should I Do Now?" Recommendation Engine."""

import pytest
from datetime import datetime, timezone
from dataclasses import dataclass

from app.core.operator_recommendation import (
    OperatorRecommendation,
    generate_operator_recommendation,
)


# Mock ExecutionPlan for testing
@dataclass
class MockExecutionPlan:
    """Mock ExecutionPlan for testing."""
    symbol: str
    action: str  # CLOSE | ROLL | HOLD | ALERT
    confidence: str  # HIGH | MEDIUM | LOW
    parameters: dict = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class TestNowPriority:
    """Test NOW priority (CLOSE/ROLL with HIGH confidence)."""
    
    def test_now_priority_with_close_high(self):
        """Test NOW priority for CLOSE with HIGH confidence."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOW"
        assert recommendation.symbol == "AAPL"
        assert recommendation.action == "CLOSE"
        assert recommendation.confidence == "HIGH"
        assert "Immediate action required" in recommendation.reason
        assert recommendation.next_check_minutes == 15
    
    def test_now_priority_with_roll_high(self):
        """Test NOW priority for ROLL with HIGH confidence."""
        plans = [
            MockExecutionPlan(
                symbol="MSFT",
                action="ROLL",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOW"
        assert recommendation.symbol == "MSFT"
        assert recommendation.action == "ROLL"
        assert recommendation.confidence == "HIGH"
        assert "Immediate action required" in recommendation.reason
    
    def test_now_priority_takes_precedence_over_soon(self):
        """Test that NOW priority takes precedence over SOON."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="MEDIUM",  # SOON
            ),
            MockExecutionPlan(
                symbol="MSFT",
                action="ROLL",
                confidence="HIGH",  # NOW
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOW"
        assert recommendation.symbol == "MSFT"
        assert recommendation.action == "ROLL"
        assert recommendation.confidence == "HIGH"


class TestSoonPriority:
    """Test SOON priority (CLOSE/ROLL with MEDIUM confidence)."""
    
    def test_soon_priority_with_close_medium(self):
        """Test SOON priority for CLOSE with MEDIUM confidence."""
        plans = [
            MockExecutionPlan(
                symbol="SPY",
                action="CLOSE",
                confidence="MEDIUM",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "SOON"
        assert recommendation.symbol == "SPY"
        assert recommendation.action == "CLOSE"
        assert recommendation.confidence == "MEDIUM"
        assert "Action recommended soon" in recommendation.reason
        assert recommendation.next_check_minutes == 30
    
    def test_soon_priority_with_roll_medium(self):
        """Test SOON priority for ROLL with MEDIUM confidence."""
        plans = [
            MockExecutionPlan(
                symbol="NVDA",
                action="ROLL",
                confidence="MEDIUM",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "SOON"
        assert recommendation.symbol == "NVDA"
        assert recommendation.action == "ROLL"
        assert recommendation.confidence == "MEDIUM"
    
    def test_soon_priority_takes_precedence_over_monitor(self):
        """Test that SOON priority takes precedence over MONITOR."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="HOLD",
                confidence="HIGH",  # MONITOR
            ),
            MockExecutionPlan(
                symbol="MSFT",
                action="CLOSE",
                confidence="MEDIUM",  # SOON
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "SOON"
        assert recommendation.symbol == "MSFT"
        assert recommendation.action == "CLOSE"
        assert recommendation.confidence == "MEDIUM"


class TestMonitorPriority:
    """Test MONITOR priority (HOLD or ALERT)."""
    
    def test_monitor_priority_with_hold(self):
        """Test MONITOR priority for HOLD action."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="HOLD",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "MONITOR"
        assert recommendation.symbol == "AAPL"
        assert recommendation.action == "HOLD"
        assert "Monitor" in recommendation.reason
        assert recommendation.next_check_minutes == 60
    
    def test_monitor_priority_with_alert(self):
        """Test MONITOR priority for ALERT action."""
        plans = [
            MockExecutionPlan(
                symbol="MSFT",
                action="ALERT",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "MONITOR"
        assert recommendation.symbol == "MSFT"
        assert recommendation.action == "ALERT"
        assert "Monitor" in recommendation.reason


class TestNothingPriority:
    """Test NOTHING priority (no actionable plans)."""
    
    def test_nothing_priority_with_empty_plans(self):
        """Test NOTHING priority with empty plans list."""
        plans = []
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOTHING"
        assert recommendation.symbol is None
        assert recommendation.action is None
        assert recommendation.confidence is None
        assert "No execution plans available" in recommendation.reason
        assert recommendation.next_check_minutes == 60
    
    def test_nothing_priority_with_no_actionable_plans(self):
        """Test NOTHING priority when all plans are filtered out."""
        # This shouldn't happen in practice, but test edge case
        plans = [None]
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOTHING"
        assert "No actionable execution plans" in recommendation.reason


class TestTieBreaking:
    """Test tie-breaking logic."""
    
    def test_tie_break_by_confidence_high_vs_medium(self):
        """Test tie-breaking by confidence (HIGH > MEDIUM)."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="MEDIUM",
            ),
            MockExecutionPlan(
                symbol="MSFT",
                action="CLOSE",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should select HIGH confidence
        assert recommendation.symbol == "MSFT"
        assert recommendation.confidence == "HIGH"
    
    def test_tie_break_by_confidence_high_vs_low(self):
        """Test tie-breaking by confidence (HIGH > LOW)."""
        plans = [
            MockExecutionPlan(
                symbol="SPY",
                action="ROLL",
                confidence="LOW",
            ),
            MockExecutionPlan(
                symbol="NVDA",
                action="ROLL",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should select HIGH confidence
        assert recommendation.symbol == "NVDA"
        assert recommendation.confidence == "HIGH"
    
    def test_tie_break_by_confidence_medium_vs_low(self):
        """Test tie-breaking by confidence (MEDIUM > LOW)."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="LOW",
            ),
            MockExecutionPlan(
                symbol="MSFT",
                action="CLOSE",
                confidence="MEDIUM",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should select MEDIUM confidence
        assert recommendation.symbol == "MSFT"
        assert recommendation.confidence == "MEDIUM"
    
    def test_tie_break_same_confidence_selects_first(self):
        """Test that same confidence selects first plan."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="HIGH",
            ),
            MockExecutionPlan(
                symbol="MSFT",
                action="CLOSE",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should select first plan (AAPL)
        assert recommendation.symbol == "AAPL"
        assert recommendation.confidence == "HIGH"


class TestOperatorRecommendationStructure:
    """Test OperatorRecommendation dataclass structure."""
    
    def test_operator_recommendation_has_all_required_fields(self):
        """Test that OperatorRecommendation has all required fields."""
        recommendation = OperatorRecommendation(
            priority="NOW",
            symbol="AAPL",
            action="CLOSE",
            confidence="HIGH",
            reason="Test reason",
            next_check_minutes=15,
        )
        
        assert hasattr(recommendation, "priority")
        assert hasattr(recommendation, "symbol")
        assert hasattr(recommendation, "action")
        assert hasattr(recommendation, "confidence")
        assert hasattr(recommendation, "reason")
        assert hasattr(recommendation, "next_check_minutes")
        assert hasattr(recommendation, "generated_at")
        
        assert recommendation.priority == "NOW"
        assert recommendation.symbol == "AAPL"
        assert recommendation.action == "CLOSE"
        assert recommendation.confidence == "HIGH"
        assert recommendation.reason == "Test reason"
        assert recommendation.next_check_minutes == 15
        assert isinstance(recommendation.generated_at, str)
    
    def test_generated_at_is_iso_format(self):
        """Test that generated_at is in ISO format."""
        recommendation = generate_operator_recommendation([])
        
        # Should be parseable as ISO datetime
        try:
            datetime.fromisoformat(recommendation.generated_at.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"generated_at is not valid ISO format: {recommendation.generated_at}")


class TestDeterministicOutput:
    """Test that recommendation generation is deterministic."""
    
    def test_same_inputs_produce_same_output(self):
        """Test that same inputs produce same output."""
        plans = [
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="HIGH",
            ),
        ]
        
        recommendation1 = generate_operator_recommendation(plans)
        recommendation2 = generate_operator_recommendation(plans)
        
        assert recommendation1.priority == recommendation2.priority
        assert recommendation1.symbol == recommendation2.symbol
        assert recommendation1.action == recommendation2.action
        assert recommendation1.confidence == recommendation2.confidence


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_handles_missing_attributes_gracefully(self):
        """Test that missing attributes are handled gracefully."""
        # Create a plan-like object with minimal attributes
        class MinimalPlan:
            def __init__(self):
                self.symbol = "AAPL"
                self.action = "CLOSE"
                # Missing confidence
        
        plans = [MinimalPlan()]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should still produce a recommendation (may default to MONITOR or handle gracefully)
        assert recommendation.priority in ["NOW", "SOON", "MONITOR", "NOTHING"]
    
    def test_handles_none_plans(self):
        """Test that None plans are filtered out."""
        plans = [
            None,
            MockExecutionPlan(
                symbol="AAPL",
                action="CLOSE",
                confidence="HIGH",
            ),
        ]
        
        recommendation = generate_operator_recommendation(plans)
        
        # Should use the valid plan
        assert recommendation.priority == "NOW"
        assert recommendation.symbol == "AAPL"
    
    def test_handles_empty_plan_list(self):
        """Test that empty plan list returns NOTHING."""
        plans = []
        
        recommendation = generate_operator_recommendation(plans)
        
        assert recommendation.priority == "NOTHING"
        assert recommendation.symbol is None
        assert recommendation.action is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
