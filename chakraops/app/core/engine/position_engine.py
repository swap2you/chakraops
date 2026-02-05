#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position engine for enforcing high-level position rules.

This engine is focused on *decision enforcement* around positions:
- It coordinates with :class:`PositionStore` for persistence.
- It applies simple invariants (e.g. only one open CSP per symbol).

No UI code, alerts, or trading/risk logic should live here.
"""

from __future__ import annotations

from typing import List

from app.core.models.position import Position
from app.core.storage.position_store import PositionStore


class PositionRuleError(RuntimeError):
    """Raised when a position rule or invariant is violated."""


class PositionEngine:
    """Engine responsible for enforcing position-level rules."""

    def __init__(self, store: PositionStore | None = None) -> None:
        """Create a new ``PositionEngine``.

        Parameters
        ----------
        store:
            Optional ``PositionStore`` instance. If not provided, a default
            store will be created pointing at the standard database path.
        """
        self.store = store or PositionStore()

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #
    def has_open_position(self, symbol: str) -> bool:
        """Return True if there is any OPEN position for the given symbol."""
        symbol = symbol.upper()
        positions = self.store.fetch_positions_by_symbol(symbol)
        return any(p.status == "OPEN" for p in positions)

    def get_open_positions(self) -> List[Position]:
        """Return all OPEN positions."""
        return self.store.fetch_all_open_positions()

    # ------------------------------------------------------------------ #
    # Mutation helpers
    # ------------------------------------------------------------------ #
    def register_new_position(self, position: Position) -> None:
        """Register a new position after enforcing engine rules.

        Rules enforced
        --------------
        - Only **one** open CSP per symbol is allowed at a time.
          If an OPEN CSP already exists for the symbol, a
          :class:`PositionRuleError` is raised.
        """
        symbol = position.symbol.upper()

        # Enforce single-open-CSP-per-symbol rule
        if position.position_type == "CSP":
            existing = self.store.fetch_positions_by_symbol(symbol)
            if any(p.position_type == "CSP" and p.status == "OPEN" for p in existing):
                raise PositionRuleError(
                    f"Cannot open new CSP for {symbol}: an OPEN CSP already exists."
                )

        # Persist the position
        self.store.insert_position(position)

    def close_position(self, position_id: str, reason: str) -> None:
        """Mark an existing position as CLOSED.

        Parameters
        ----------
        position_id:
            Identifier of the position to close.
        reason:
            Textual reason for closure (currently unused, but may be logged
            or persisted by higher layers).

        Notes
        -----
        - This method enforces state machine transitions.
        - If position is OPEN, transitions to CLOSING first, then CLOSED.
        - If position is CLOSING, transitions directly to CLOSED.
        - If the position does not exist, the store's update will be a no-op;
          callers that require strict behavior should verify existence before
          calling this method.
        """
        # Fetch current position to determine state
        positions = self.store.fetch_all_open_positions()
        position = next((p for p in positions if p.id == position_id), None)
        
        if not position:
            # Try to find any position with this ID
            # For now, just update status (backward compatibility)
            self.store.update_position_status(position_id, "CLOSED", action="CLOSE")
            return
        
        # Get current state
        from app.core.state_machine import PositionState, PositionAction, next_state
        
        current_state_str = position.state or "OPEN"
        state_mapping = {
            "NEW": PositionState.NEW,
            "ASSIGNED": PositionState.ASSIGNED,
            "OPEN": PositionState.OPEN,
            "ROLLING": PositionState.ROLLING,
            "CLOSING": PositionState.CLOSING,
            "CLOSED": PositionState.CLOSED,
        }
        current_state = state_mapping.get(current_state_str, PositionState.OPEN)
        
        # Determine action based on current state
        if current_state == PositionState.OPEN:
            # First transition: OPEN -> CLOSING
            self.store.update_position_status(position_id, "CLOSING", action="CLOSE")
            # Then transition: CLOSING -> CLOSED
            self.store.update_position_status(position_id, "CLOSED", action="CLOSE")
        elif current_state == PositionState.CLOSING:
            # Direct transition: CLOSING -> CLOSED
            self.store.update_position_status(position_id, "CLOSED", action="CLOSE")
        else:
            # For other states, just update status (may fail validation)
            self.store.update_position_status(position_id, "CLOSED", action="CLOSE")


__all__ = ["PositionEngine", "PositionRuleError"]

