# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position lifecycle states and event tracking (Phase 6.3).

Persistent position lifecycle: PROPOSED -> OPEN -> PARTIALLY_CLOSED | CLOSED | ASSIGNED.
Events form an audit trail (OPENED, TARGET_1_HIT, STOP_TRIGGERED, CLOSED, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Set


class PositionLifecycleState(str, Enum):
    """Lifecycle state for a position. Valid transitions are enforced."""

    PROPOSED = "PROPOSED"
    OPEN = "OPEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    CLOSED = "CLOSED"
    ASSIGNED = "ASSIGNED"


class PositionEventType(str, Enum):
    """Event types for position event tracking."""

    OPENED = "OPENED"
    TARGET_1_HIT = "TARGET_1_HIT"
    TARGET_2_HIT = "TARGET_2_HIT"
    STOP_TRIGGERED = "STOP_TRIGGERED"
    ASSIGNED = "ASSIGNED"
    CLOSED = "CLOSED"
    MANUAL_NOTE = "MANUAL_NOTE"


# Allowed lifecycle transitions: from_state -> set of to_states
ALLOWED_LIFECYCLE_TRANSITIONS: Dict[PositionLifecycleState, Set[PositionLifecycleState]] = {
    PositionLifecycleState.PROPOSED: {PositionLifecycleState.OPEN, PositionLifecycleState.CLOSED},
    PositionLifecycleState.OPEN: {
        PositionLifecycleState.PARTIALLY_CLOSED,
        PositionLifecycleState.CLOSED,
        PositionLifecycleState.ASSIGNED,
    },
    PositionLifecycleState.PARTIALLY_CLOSED: {PositionLifecycleState.OPEN, PositionLifecycleState.CLOSED},
    PositionLifecycleState.CLOSED: set(),  # Terminal
    PositionLifecycleState.ASSIGNED: {PositionLifecycleState.CLOSED},
}


class InvalidLifecycleTransitionError(Exception):
    """Raised when an invalid lifecycle state transition is attempted."""

    def __init__(
        self,
        position_id: str,
        from_state: str,
        to_state: str,
    ) -> None:
        self.position_id = position_id
        self.from_state = from_state
        self.to_state = to_state
        allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(
            PositionLifecycleState(from_state) if from_state else PositionLifecycleState.OPEN,
            set(),
        )
        allowed_str = ", ".join(s.value for s in allowed) if allowed else "none (terminal)"
        super().__init__(
            f"Invalid lifecycle transition for position {position_id}: "
            f"{from_state} -> {to_state}. Allowed from {from_state}: {allowed_str}"
        )


def validate_lifecycle_transition(
    from_state: str,
    to_state: str,
    position_id: str = "",
) -> None:
    """Validate that a lifecycle transition is allowed. Raises InvalidLifecycleTransitionError if not."""
    try:
        from_enum = PositionLifecycleState(from_state) if from_state else PositionLifecycleState.OPEN
    except ValueError:
        from_enum = PositionLifecycleState.OPEN
    try:
        to_enum = PositionLifecycleState(to_state)
    except ValueError:
        raise InvalidLifecycleTransitionError(position_id, from_state or "OPEN", to_state)
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(from_enum, set())
    if to_enum not in allowed:
        raise InvalidLifecycleTransitionError(position_id, from_state or "OPEN", to_state)


@dataclass
class PositionEvent:
    """A single position event (audit trail)."""

    position_id: str
    event_type: str  # PositionEventType value
    event_time: str  # ISO datetime
    metadata: Dict[str, Any]  # JSON-serializable


def make_position_event(
    position_id: str,
    event_type: PositionEventType,
    metadata: Dict[str, Any] | None = None,
) -> PositionEvent:
    """Create a PositionEvent with current timestamp."""
    return PositionEvent(
        position_id=position_id,
        event_type=event_type.value,
        event_time=datetime.now(timezone.utc).isoformat(),
        metadata=metadata or {},
    )


__all__ = [
    "PositionLifecycleState",
    "PositionEventType",
    "PositionEvent",
    "ALLOWED_LIFECYCLE_TRANSITIONS",
    "InvalidLifecycleTransitionError",
    "validate_lifecycle_transition",
    "make_position_event",
]
