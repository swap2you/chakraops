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
        - This method only updates the status to ``\"CLOSED\"`` in the store.
        - If the position does not exist, the store's update will be a no-op;
          callers that require strict behavior should verify existence before
          calling this method.
        """
        # Delegate to the store; enforcement/logging can be layered on top later.
        self.store.update_position_status(position_id, "CLOSED")


__all__ = ["PositionEngine", "PositionRuleError"]

