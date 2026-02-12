# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for strict position state machine enforcement."""

import pytest
from datetime import datetime, timezone

from app.core.state_machine import (
    PositionState,
    PositionAction,
    InvalidTransitionError,
    validate_transition,
    next_state,
    get_allowed_actions,
)


class TestValidTransitions:
    """Test valid state transitions."""
    
    def test_new_to_assigned_with_assign_action(self):
        """Test NEW -> ASSIGNED with ASSIGN action."""
        to_state = next_state(PositionState.NEW, PositionAction.ASSIGN)
        assert to_state == PositionState.ASSIGNED
        
        # Validate should not raise
        validate_transition("AAPL", PositionState.NEW, PositionAction.ASSIGN, PositionState.ASSIGNED)
    
    def test_assigned_to_open_with_open_action(self):
        """Test ASSIGNED -> OPEN with OPEN action."""
        to_state = next_state(PositionState.ASSIGNED, PositionAction.OPEN)
        assert to_state == PositionState.OPEN
        
        validate_transition("AAPL", PositionState.ASSIGNED, PositionAction.OPEN, PositionState.OPEN)
    
    def test_open_to_open_with_hold_action_idempotent(self):
        """Test OPEN -> OPEN with HOLD action (idempotent)."""
        to_state = next_state(PositionState.OPEN, PositionAction.HOLD)
        assert to_state == PositionState.OPEN
        
        validate_transition("AAPL", PositionState.OPEN, PositionAction.HOLD, PositionState.OPEN)
    
    def test_open_to_rolling_with_roll_action(self):
        """Test OPEN -> ROLLING with ROLL action."""
        to_state = next_state(PositionState.OPEN, PositionAction.ROLL)
        assert to_state == PositionState.ROLLING
        
        validate_transition("AAPL", PositionState.OPEN, PositionAction.ROLL, PositionState.ROLLING)
    
    def test_rolling_to_open_with_open_action(self):
        """Test ROLLING -> OPEN with OPEN action (after roll executed)."""
        to_state = next_state(PositionState.ROLLING, PositionAction.OPEN)
        assert to_state == PositionState.OPEN
        
        validate_transition("AAPL", PositionState.ROLLING, PositionAction.OPEN, PositionState.OPEN)
    
    def test_open_to_closing_with_close_action(self):
        """Test OPEN -> CLOSING with CLOSE action."""
        to_state = next_state(PositionState.OPEN, PositionAction.CLOSE)
        assert to_state == PositionState.CLOSING
        
        validate_transition("AAPL", PositionState.OPEN, PositionAction.CLOSE, PositionState.CLOSING)
    
    def test_closing_to_closed_with_close_action(self):
        """Test CLOSING -> CLOSED with CLOSE action."""
        to_state = next_state(PositionState.CLOSING, PositionAction.CLOSE)
        assert to_state == PositionState.CLOSED
        
        validate_transition("AAPL", PositionState.CLOSING, PositionAction.CLOSE, PositionState.CLOSED)


class TestInvalidTransitions:
    """Test invalid state transitions."""
    
    def test_closed_to_open_raises_error(self):
        """Test that CLOSED -> OPEN raises InvalidTransitionError."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "AAPL",
                PositionState.CLOSED,
                PositionAction.OPEN,
                PositionState.OPEN
            )
        
        assert "AAPL" in str(exc_info.value)
        assert "CLOSED" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)
    
    def test_new_to_open_raises_error(self):
        """Test that NEW -> OPEN (without ASSIGN first) raises error."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "MSFT",
                PositionState.NEW,
                PositionAction.OPEN,
                PositionState.OPEN
            )
        
        assert "MSFT" in str(exc_info.value)
        assert "NEW" in str(exc_info.value)
    
    def test_open_to_closed_directly_raises_error(self):
        """Test that OPEN -> CLOSED (without CLOSING) raises error."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "NVDA",
                PositionState.OPEN,
                PositionAction.CLOSE,
                PositionState.CLOSED  # Wrong: should be CLOSING
            )
        
        assert "NVDA" in str(exc_info.value)
    
    def test_rolling_to_closed_directly_raises_error(self):
        """Test that ROLLING -> CLOSED raises error."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(
                "SPY",
                PositionState.ROLLING,
                PositionAction.CLOSE,
                PositionState.CLOSED
            )
    
    def test_assigned_to_rolling_raises_error(self):
        """Test that ASSIGNED -> ROLLING raises error."""
        with pytest.raises(InvalidTransitionError):
            validate_transition(
                "TSLA",
                PositionState.ASSIGNED,
                PositionAction.ROLL,
                PositionState.ROLLING
            )
    
    def test_next_state_invalid_combination_raises_error(self):
        """Test that next_state raises error for invalid combinations."""
        with pytest.raises(InvalidTransitionError):
            next_state(PositionState.CLOSED, PositionAction.OPEN)
        
        with pytest.raises(InvalidTransitionError):
            next_state(PositionState.NEW, PositionAction.OPEN)


class TestIdempotentHold:
    """Test idempotent HOLD action on OPEN state."""
    
    def test_hold_on_open_is_idempotent(self):
        """Test that HOLD action on OPEN state is idempotent."""
        # First HOLD
        state1 = next_state(PositionState.OPEN, PositionAction.HOLD)
        assert state1 == PositionState.OPEN
        
        # Second HOLD (should still be OPEN)
        state2 = next_state(state1, PositionAction.HOLD)
        assert state2 == PositionState.OPEN
        
        # Can validate multiple times
        validate_transition("AAPL", PositionState.OPEN, PositionAction.HOLD, PositionState.OPEN)
        validate_transition("AAPL", PositionState.OPEN, PositionAction.HOLD, PositionState.OPEN)


class TestGetAllowedActions:
    """Test get_allowed_actions function."""
    
    def test_allowed_actions_from_new(self):
        """Test allowed actions from NEW state."""
        actions = get_allowed_actions(PositionState.NEW)
        assert PositionAction.ASSIGN in actions
        assert len(actions) == 1
    
    def test_allowed_actions_from_assigned(self):
        """Test allowed actions from ASSIGNED state."""
        actions = get_allowed_actions(PositionState.ASSIGNED)
        assert PositionAction.OPEN in actions
        assert len(actions) == 1
    
    def test_allowed_actions_from_open(self):
        """Test allowed actions from OPEN state."""
        actions = get_allowed_actions(PositionState.OPEN)
        assert PositionAction.HOLD in actions
        assert PositionAction.ROLL in actions
        assert PositionAction.CLOSE in actions
        assert len(actions) == 3
    
    def test_allowed_actions_from_rolling(self):
        """Test allowed actions from ROLLING state."""
        actions = get_allowed_actions(PositionState.ROLLING)
        assert PositionAction.OPEN in actions
        assert len(actions) == 1
    
    def test_allowed_actions_from_closing(self):
        """Test allowed actions from CLOSING state."""
        actions = get_allowed_actions(PositionState.CLOSING)
        assert PositionAction.CLOSE in actions
        assert len(actions) == 1
    
    def test_allowed_actions_from_closed(self):
        """Test allowed actions from CLOSED state (terminal)."""
        actions = get_allowed_actions(PositionState.CLOSED)
        assert len(actions) == 0  # Terminal state


class TestErrorMessages:
    """Test error message formatting."""
    
    def test_error_message_includes_symbol(self):
        """Test that error message includes symbol."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "TEST_SYMBOL",
                PositionState.CLOSED,
                PositionAction.OPEN,
                PositionState.OPEN
            )
        
        assert "TEST_SYMBOL" in str(exc_info.value)
    
    def test_error_message_includes_states_and_action(self):
        """Test that error message includes from_state, action, and to_state."""
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "AAPL",
                PositionState.NEW,
                PositionAction.OPEN,
                PositionState.OPEN
            )
        
        error_str = str(exc_info.value)
        assert "NEW" in error_str
        assert "OPEN" in error_str
        assert "ASSIGN" in error_str  # Should mention allowed action
    
    def test_error_with_correlation_id(self):
        """Test that correlation_id is included in error if provided."""
        correlation_id = "test-correlation-123"
        
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition(
                "AAPL",
                PositionState.CLOSED,
                PositionAction.OPEN,
                PositionState.OPEN,
                correlation_id=correlation_id
            )
        
        assert correlation_id in str(exc_info.value)
        assert exc_info.value.correlation_id == correlation_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
