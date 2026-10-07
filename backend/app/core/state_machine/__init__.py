# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Strict position state machine with action-based transitions.

This module provides a canonical source of truth for position states and actions,
with strict enforcement of valid transitions. All state changes must go through
the validation functions in this module.
"""

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PositionState(Enum):
    """Canonical position states - single source of truth."""
    
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    OPEN = "OPEN"
    ROLLING = "ROLLING"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


class PositionAction(Enum):
    """Canonical position actions - single source of truth."""
    
    ASSIGN = "ASSIGN"
    OPEN = "OPEN"
    HOLD = "HOLD"
    ROLL = "ROLL"
    CLOSE = "CLOSE"


# Define allowed transitions: (from_state, action) -> to_state
# This is the single source of truth for valid transitions
TRANSITION_MAP: Dict[Tuple[PositionState, PositionAction], PositionState] = {
    # NEW -> ASSIGNED (action ASSIGN)
    (PositionState.NEW, PositionAction.ASSIGN): PositionState.ASSIGNED,
    
    # ASSIGNED -> OPEN (action OPEN)
    (PositionState.ASSIGNED, PositionAction.OPEN): PositionState.OPEN,
    
    # OPEN -> OPEN (action HOLD) [idempotent]
    (PositionState.OPEN, PositionAction.HOLD): PositionState.OPEN,
    
    # OPEN -> ROLLING (action ROLL)
    (PositionState.OPEN, PositionAction.ROLL): PositionState.ROLLING,
    
    # ROLLING -> OPEN (action OPEN) [after roll executed]
    (PositionState.ROLLING, PositionAction.OPEN): PositionState.OPEN,
    
    # OPEN -> CLOSING (action CLOSE)
    (PositionState.OPEN, PositionAction.CLOSE): PositionState.CLOSING,
    
    # CLOSING -> CLOSED (action CLOSE)
    (PositionState.CLOSING, PositionAction.CLOSE): PositionState.CLOSED,
}


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    
    def __init__(
        self,
        symbol: str,
        from_state: PositionState,
        action: PositionAction,
        to_state: PositionState,
        correlation_id: Optional[str] = None,
    ) -> None:
        self.symbol = symbol
        self.from_state = from_state
        self.action = action
        self.to_state = to_state
        self.correlation_id = correlation_id
        
        # Find allowed transitions from from_state
        allowed_actions = [
            action for (state, action), target in TRANSITION_MAP.items()
            if state == from_state
        ]
        allowed_str = ", ".join([a.value for a in allowed_actions]) if allowed_actions else "none (terminal state)"
        
        message = (
            f"Invalid transition for {symbol}: "
            f"{from_state.value} --{action.value}--> {to_state.value}. "
            f"Allowed actions from {from_state.value}: {allowed_str}"
        )
        
        if correlation_id:
            message += f" (correlation_id: {correlation_id})"
        
        super().__init__(message)


def validate_transition(
    symbol: str,
    from_state: PositionState,
    action: PositionAction,
    to_state: PositionState,
    correlation_id: Optional[str] = None,
) -> None:
    """Validate that a state transition is allowed.
    
    Parameters
    ----------
    symbol:
        Position symbol for error messages.
    from_state:
        Current state of the position.
    action:
        Action being performed.
    to_state:
        Target state after the action.
    correlation_id:
        Optional correlation ID for tracking (timestamp, request ID, etc.).
    
    Raises
    ------
    InvalidTransitionError
        If the transition is not allowed. The error is logged as ERROR
        with full context before being raised.
    """
    # Check if this transition is allowed
    expected_to_state = TRANSITION_MAP.get((from_state, action))
    
    if expected_to_state is None or expected_to_state != to_state:
        error = InvalidTransitionError(symbol, from_state, action, to_state, correlation_id)
        
        # Log as ERROR with full context
        error_msg = (
            f"Invalid transition for {symbol}: "
            f"{from_state.value} --{action.value}--> {to_state.value}"
        )
        if correlation_id:
            error_msg += f" (correlation_id: {correlation_id})"
        
        logger.error(error_msg, extra={
            "symbol": symbol,
            "from_state": from_state.value,
            "action": action.value,
            "to_state": to_state.value,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Log to alert pipeline (if available)
        try:
            # State machine errors are internal - log only, don't create alerts (Phase 1B)
            logger.error(error_msg)
        except Exception:
            pass  # Don't fail if logging fails
        
        raise error


def next_state(from_state: PositionState, action: PositionAction) -> PositionState:
    """Get the next state for a given state and action.
    
    Parameters
    ----------
    from_state:
        Current state of the position.
    action:
        Action being performed.
    
    Returns
    -------
    PositionState
        The target state after the action.
    
    Raises
    ------
    InvalidTransitionError
        If the (from_state, action) combination is not allowed.
    """
    to_state = TRANSITION_MAP.get((from_state, action))
    
    if to_state is None:
        # Find allowed actions for better error message
        allowed_actions = [
            a for (state, a), target in TRANSITION_MAP.items()
            if state == from_state
        ]
        allowed_str = ", ".join([a.value for a in allowed_actions]) if allowed_actions else "none (terminal state)"
        
        raise InvalidTransitionError(
            symbol="<unknown>",
            from_state=from_state,
            action=action,
            to_state=PositionState.CLOSED,  # Dummy value for error message
        )
    
    return to_state


def get_allowed_actions(from_state: PositionState) -> list[PositionAction]:
    """Get all allowed actions from a given state.
    
    Parameters
    ----------
    from_state:
        Current state of the position.
    
    Returns
    -------
    list[PositionAction]
        List of actions that can be performed from this state.
    """
    return [
        action for (state, action), target in TRANSITION_MAP.items()
        if state == from_state
    ]


# Re-export from position_state_machine for backward compatibility
from app.core.state_machine.position_state_machine import (
    StateTransitionEvent,
    transition_position as legacy_transition_position,
    get_allowed_transitions as legacy_get_allowed_transitions,
    PositionState as LegacyPositionState,
    ALLOWED_TRANSITIONS as LEGACY_ALLOWED_TRANSITIONS,
)

__all__ = [
    "PositionState",
    "PositionAction",
    "InvalidTransitionError",
    "validate_transition",
    "next_state",
    "get_allowed_actions",
    "TRANSITION_MAP",
    # Legacy exports
    "StateTransitionEvent",
    "legacy_transition_position",
    "legacy_get_allowed_transitions",
    "LegacyPositionState",
    "LEGACY_ALLOWED_TRANSITIONS",
]
