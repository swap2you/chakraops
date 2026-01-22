# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position state machine for enforcing valid state transitions.

This module implements a strict state machine for position lifecycle management.
All state transitions must be validated before being applied.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class PositionState(Enum):
    """Valid states for a position in the lifecycle."""
    
    NEW = "NEW"
    OPEN = "OPEN"
    HOLD = "HOLD"
    ROLL_CANDIDATE = "ROLL_CANDIDATE"
    ROLLING = "ROLLING"
    CLOSED = "CLOSED"
    ASSIGNED = "ASSIGNED"


# Define allowed transitions: from_state -> set of allowed to_states
ALLOWED_TRANSITIONS: Dict[PositionState, Set[PositionState]] = {
    PositionState.NEW: {PositionState.OPEN, PositionState.CLOSED},
    PositionState.OPEN: {PositionState.HOLD, PositionState.ROLL_CANDIDATE, PositionState.CLOSED, PositionState.ASSIGNED},
    PositionState.HOLD: {PositionState.ROLL_CANDIDATE, PositionState.CLOSED, PositionState.ASSIGNED},
    PositionState.ROLL_CANDIDATE: {PositionState.ROLLING, PositionState.HOLD, PositionState.CLOSED},
    PositionState.ROLLING: {PositionState.OPEN, PositionState.HOLD, PositionState.CLOSED, PositionState.ASSIGNED},
    PositionState.ASSIGNED: {PositionState.HOLD, PositionState.CLOSED},
    PositionState.CLOSED: set(),  # Terminal state - no transitions allowed
}


@dataclass
class StateTransitionEvent:
    """Represents a single state transition event in position history."""
    
    from_state: str
    to_state: str
    reason: str
    source: str  # e.g., "system", "user", "risk_engine"
    timestamp_iso: str


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(self, from_state: PositionState, to_state: PositionState, position_id: str) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.position_id = position_id
        allowed = ALLOWED_TRANSITIONS.get(from_state, set())
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "none (terminal state)"
        super().__init__(
            f"Invalid transition for position {position_id}: "
            f"{from_state.value} -> {to_state.value}. "
            f"Allowed transitions from {from_state.value}: {allowed_str}"
        )


def transition_position(
    position: "Position",
    new_state: PositionState,
    reason: str,
    source: str = "system",
) -> "Position":
    """Transition a position to a new state, enforcing valid transitions.
    
    Parameters
    ----------
    position:
        Position object to transition.
    new_state:
        Target state for the transition.
    reason:
        Human-readable reason for the transition.
    source:
        Source of the transition (e.g., "system", "user", "risk_engine").
    
    Returns
    -------
    Position
        Updated position with new state and appended history entry.
    
    Raises
    ------
    InvalidTransitionError
        If the transition from current state to new_state is not allowed.
    """
    from app.core.models.position import Position
    
    # Get current state (handle migration: if state is None, default to OPEN)
    current_state_str = getattr(position, 'state', None) or getattr(position, 'status', 'OPEN')
    
    # Convert string to PositionState enum
    try:
        if isinstance(current_state_str, PositionState):
            current_state = current_state_str
        else:
            # Map all state values (both old status and new states)
            state_mapping = {
                "NEW": PositionState.NEW,
                "OPEN": PositionState.OPEN,
                "HOLD": PositionState.HOLD,
                "ROLL_CANDIDATE": PositionState.ROLL_CANDIDATE,
                "ROLLING": PositionState.ROLLING,
                "ASSIGNED": PositionState.ASSIGNED,
                "CLOSED": PositionState.CLOSED,
            }
            current_state = state_mapping.get(str(current_state_str).upper(), PositionState.OPEN)
    except (AttributeError, ValueError, TypeError):
        current_state = PositionState.OPEN
    
    # Validate transition
    allowed = ALLOWED_TRANSITIONS.get(current_state, set())
    if new_state not in allowed:
        error = InvalidTransitionError(current_state, new_state, position.id)
        logger.error(f"Invalid transition: {error}")
        
        # State machine errors are internal - log only, don't create alerts (Phase 1B)
        # These should not appear in operator alerts UI
        
        raise error
    
    # Create transition event as dict (for JSON serialization)
    transition_event_dict = {
        'from_state': current_state.value,
        'to_state': new_state.value,
        'reason': reason,
        'source': source,
        'timestamp_iso': datetime.now(timezone.utc).isoformat(),
    }
    
    # Get existing state history (handle migration)
    state_history = getattr(position, 'state_history', None) or []
    if not isinstance(state_history, list):
        state_history = []
    
    # Convert StateTransitionEvent objects to dicts if needed
    normalized_history = []
    for event in state_history:
        if isinstance(event, dict):
            normalized_history.append(event)
        elif hasattr(event, '__dict__'):
            # Convert StateTransitionEvent to dict
            normalized_history.append({
                'from_state': getattr(event, 'from_state', ''),
                'to_state': getattr(event, 'to_state', ''),
                'reason': getattr(event, 'reason', ''),
                'source': getattr(event, 'source', ''),
                'timestamp_iso': getattr(event, 'timestamp_iso', ''),
            })
        else:
            normalized_history.append(event)
    
    # Append new transition
    normalized_history.append(transition_event_dict)
    
    # Update position state
    # Create a new Position with updated state and history
    position_dict = {
        'id': position.id,
        'symbol': position.symbol,
        'position_type': position.position_type,
        'strike': position.strike,
        'expiry': position.expiry,
        'contracts': position.contracts,
        'premium_collected': position.premium_collected,
        'entry_date': position.entry_date,
        'state': new_state.value,  # Store as string for JSON serialization
        'state_history': normalized_history,
        'notes': position.notes,
    }
    
    # Preserve status for backward compatibility
    if hasattr(position, 'status'):
        position_dict['status'] = position.status
    
    # Create new Position instance
    updated_position = Position(**position_dict)
    
    logger.info(
        f"Position {position.id} ({position.symbol}) transitioned: "
        f"{current_state.value} -> {new_state.value} ({source}: {reason})"
    )
    
    return updated_position


def get_allowed_transitions(current_state: PositionState) -> Set[PositionState]:
    """Get all allowed transitions from a given state.
    
    Parameters
    ----------
    current_state:
        Current state of the position.
    
    Returns
    -------
    set[PositionState]
        Set of states that can be transitioned to from current_state.
    """
    return ALLOWED_TRANSITIONS.get(current_state, set()).copy()


__all__ = [
    "PositionState",
    "StateTransitionEvent",
    "InvalidTransitionError",
    "transition_position",
    "get_allowed_transitions",
    "ALLOWED_TRANSITIONS",
]
