#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position models used by the ChakraOps engine.

This module defines light-weight, typed containers for tracking positions.
It is intentionally free of business logic; higher-level orchestration
layers are responsible for decisions and state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Literal, Optional
from uuid import uuid4

PositionType = Literal["CSP", "SHARES"]
PositionStatus = Literal["OPEN", "ASSIGNED", "CLOSED"]  # Deprecated: use state instead


@dataclass(slots=True)
class Position:
    """Represents a single trading position.

    Fields are designed to be serialization-friendly (e.g. JSON/SQLite) and
    to capture the minimal information required to reason about CSP and
    share-only positions.
    
    Note: The `status` field is deprecated in favor of `state`. For backward
    compatibility, `status` is still supported but will be automatically
    converted to `state` when accessed.
    """

    id: str
    symbol: str
    position_type: PositionType
    strike: Optional[float]
    expiry: Optional[str]  # ISO date YYYY-MM-DD
    contracts: int
    premium_collected: float
    entry_date: str        # ISO datetime
    status: PositionStatus = "OPEN"  # Deprecated: use state instead
    state: Optional[str] = None  # PositionState enum value as string
    state_history: List[Any] = field(default_factory=list)  # List of StateTransitionEvent dicts
    notes: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Initialize state from status if state is not set (migration)."""
        # If state is not set but status is, migrate status to state
        if self.state is None and self.status:
            # Map old status to new state
            status_to_state = {
                "OPEN": "OPEN",
                "ASSIGNED": "ASSIGNED",
                "CLOSED": "CLOSED",
            }
            self.state = status_to_state.get(self.status, "OPEN")
        
        # Ensure state_history is a list
        if self.state_history is None:
            self.state_history = []

    # --------------------------------------------------------------------- #
    # Factory helpers
    # --------------------------------------------------------------------- #
    @staticmethod
    def create_csp(
        symbol: str,
        strike: float,
        expiry: str,
        contracts: int,
        premium_collected: float,
        notes: Optional[str] = None,
    ) -> "Position":
        """Create a cash-secured put position.

        Parameters
        ----------
        symbol:
            Underlying ticker (e.g. \"SPY\").
        strike:
            Option strike price.
        expiry:
            Expiration date as ISO string (YYYY-MM-DD).
        contracts:
            Number of option contracts (positive integer).
        premium_collected:
            Total premium collected (per-contract premium * contracts).
        notes:
            Optional free-form notes.
        """
        return Position(
            id=str(uuid4()),
            symbol=symbol.upper(),
            position_type="CSP",
            strike=float(strike),
            expiry=expiry,
            contracts=int(contracts),
            premium_collected=float(premium_collected),
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="NEW",  # New positions start in NEW state
            state_history=[],
            notes=notes,
        )

    @staticmethod
    def create_shares(
        symbol: str,
        shares: int,
        notes: Optional[str] = None,
    ) -> "Position":
        """Create a share-only position.

        Parameters
        ----------
        symbol:
            Underlying ticker (e.g. \"SPY\").
        shares:
            Number of shares held (positive integer).
        notes:
            Optional free-form notes.
        """
        return Position(
            id=str(uuid4()),
            symbol=symbol.upper(),
            position_type="SHARES",
            strike=None,
            expiry=None,
            contracts=int(shares),
            premium_collected=0.0,
            entry_date=datetime.now(timezone.utc).isoformat(),
            status="OPEN",
            state="NEW",  # New positions start in NEW state
            state_history=[],
            notes=notes,
        )


__all__ = ["Position", "PositionType", "PositionStatus"]

