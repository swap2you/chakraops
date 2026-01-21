# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for position state machine."""

import pytest
from datetime import datetime, timezone

from app.core.models.position import Position
from app.core.state_machine.position_state_machine import (
    PositionState,
    InvalidTransitionError,
    transition_position,
    get_allowed_transitions,
    StateTransitionEvent,
)


class TestValidTransitions:
    """Test valid state transitions."""
    
    def test_valid_transition_open_to_hold(self):
        """Test that OPEN -> HOLD transition is allowed."""
        position = Position(
            id="test-1",
            symbol="AAPL",
            position_type="CSP",
            strike=150.0,
            expiry="2026-03-21",
            contracts=1,
            premium_collected=300.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        updated = transition_position(
            position,
            PositionState.HOLD,
            "Price above EMA200, holding position",
            source="risk_engine"
        )
        
        assert updated.state == "HOLD"  # Stored as string
        assert len(updated.state_history) == 1
        # state_history is a list of dicts
        assert updated.state_history[0]['from_state'] == "OPEN"
        assert updated.state_history[0]['to_state'] == "HOLD"
        assert updated.state_history[0]['reason'] == "Price above EMA200, holding position"
        assert updated.state_history[0]['source'] == "risk_engine"
    
    def test_valid_transition_new_to_open(self):
        """Test that NEW -> OPEN transition is allowed."""
        position = Position(
            id="test-2",
            symbol="MSFT",
            position_type="CSP",
            strike=200.0,
            expiry="2026-04-15",
            contracts=2,
            premium_collected=500.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="NEW",
            state_history=[],
        )
        
        updated = transition_position(
            position,
            PositionState.OPEN,
            "Position opened",
            source="system"
        )
        
        assert updated.state == "OPEN"  # Stored as string
        assert len(updated.state_history) == 1


class TestInvalidTransitions:
    """Test invalid state transitions."""
    
    def test_invalid_transition_closed_to_open(self):
        """Test that CLOSED -> OPEN transition is not allowed."""
        position = Position(
            id="test-3",
            symbol="NVDA",
            position_type="CSP",
            strike=300.0,
            expiry="2026-02-28",
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="CLOSED",
            state="CLOSED",
            state_history=[],
        )
        
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition_position(
                position,
                PositionState.OPEN,
                "Attempting to reopen closed position",
                source="user"
            )
        
        assert exc_info.value.from_state == PositionState.CLOSED
        assert exc_info.value.to_state == PositionState.OPEN
        assert "CLOSED" in str(exc_info.value)
        assert "OPEN" in str(exc_info.value)
    
    def test_invalid_transition_new_to_assigned(self):
        """Test that NEW -> ASSIGNED transition is not allowed."""
        position = Position(
            id="test-4",
            symbol="AMZN",
            position_type="CSP",
            strike=100.0,
            expiry="2026-03-15",
            contracts=1,
            premium_collected=200.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="NEW",
            state_history=[],
        )
        
        with pytest.raises(InvalidTransitionError):
            transition_position(
                position,
                PositionState.ASSIGNED,
                "Invalid direct assignment",
                source="system"
            )


class TestStateHistory:
    """Test state history tracking."""
    
    def test_history_is_appended(self):
        """Test that state history is properly appended on each transition."""
        position = Position(
            id="test-5",
            symbol="META",
            position_type="CSP",
            strike=250.0,
            expiry="2026-05-20",
            contracts=1,
            premium_collected=350.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="NEW",
            state_history=[],
        )
        
        # First transition: NEW -> OPEN
        position = transition_position(
            position,
            PositionState.OPEN,
            "Position opened",
            source="system"
        )
        assert len(position.state_history) == 1
        
        # Second transition: OPEN -> HOLD
        position = transition_position(
            position,
            PositionState.HOLD,
            "Holding position",
            source="risk_engine"
        )
        assert len(position.state_history) == 2
        
        # Verify history entries (state_history is list of dicts)
        assert position.state_history[0]['from_state'] == "NEW"
        assert position.state_history[0]['to_state'] == "OPEN"
        assert position.state_history[1]['from_state'] == "OPEN"
        assert position.state_history[1]['to_state'] == "HOLD"
    
    def test_history_timestamps(self):
        """Test that state history includes timestamps."""
        position = Position(
            id="test-6",
            symbol="GOOGL",
            position_type="CSP",
            strike=120.0,
            expiry="2026-06-15",
            contracts=1,
            premium_collected=250.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="OPEN",
            state_history=[],
        )
        
        updated = transition_position(
            position,
            PositionState.HOLD,
            "Test transition",
            source="test"
        )
        
        assert len(updated.state_history) == 1
        assert updated.state_history[0]['timestamp_iso'] is not None
        assert "T" in updated.state_history[0]['timestamp_iso']  # ISO format check


class TestMigration:
    """Test migration from old status to new state."""
    
    def test_migration_defaults_state_to_open(self):
        """Test that positions without state default to OPEN."""
        # Create position with only status (old format)
        position = Position(
            id="test-7",
            symbol="TSLA",
            position_type="CSP",
            strike=180.0,
            expiry="2026-07-20",
            contracts=1,
            premium_collected=400.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state=None,  # Old format - no state
            state_history=None,  # Old format - no history
        )
        
        # Position should migrate state from status in __post_init__
        # But for testing, let's verify transition_position handles it
        updated = transition_position(
            position,
            PositionState.HOLD,
            "Migration test",
            source="system"
        )
        
        # Should have migrated from OPEN (derived from status) to HOLD
        assert updated.state == "HOLD"  # Stored as string
        assert len(updated.state_history) == 1
        assert updated.state_history[0]['from_state'] == "OPEN"
        assert updated.state_history[0]['to_state'] == "HOLD"


class TestAllowedTransitions:
    """Test getting allowed transitions."""
    
    def test_get_allowed_transitions_open(self):
        """Test allowed transitions from OPEN state."""
        allowed = get_allowed_transitions(PositionState.OPEN)
        assert PositionState.HOLD in allowed
        assert PositionState.ROLL_CANDIDATE in allowed
        assert PositionState.CLOSED in allowed
        assert PositionState.ASSIGNED in allowed
        assert PositionState.NEW not in allowed
        assert PositionState.ROLLING not in allowed
    
    def test_get_allowed_transitions_closed(self):
        """Test that CLOSED has no allowed transitions (terminal state)."""
        allowed = get_allowed_transitions(PositionState.CLOSED)
        assert len(allowed) == 0
    
    def test_get_allowed_transitions_rolling(self):
        """Test allowed transitions from ROLLING state."""
        allowed = get_allowed_transitions(PositionState.ROLLING)
        assert PositionState.OPEN in allowed
        assert PositionState.HOLD in allowed
        assert PositionState.CLOSED in allowed
        assert PositionState.ASSIGNED in allowed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
