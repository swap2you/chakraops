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
from typing import TYPE_CHECKING, Any, List, Literal, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from app.models.exit_plan import ExitPlan

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
    exit_plan: Optional[Any] = None  # ExitPlan (formal stop/profit/time/regime rules)
    # Phase 6.3: persistent lifecycle and PnL
    entry_credit: Optional[float] = None  # Credit at entry (defaults to premium_collected)
    open_date: Optional[str] = None      # ISO date YYYY-MM-DD (defaults to entry_date date part)
    close_date: Optional[str] = None     # ISO date when closed (nullable)
    realized_pnl: Optional[float] = None # Realized P&L when closed/partial
    lifecycle_state: Optional[str] = None  # PositionLifecycleState: PROPOSED, OPEN, PARTIALLY_CLOSED, CLOSED, ASSIGNED

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

        # Phase 6.3: defaults for lifecycle fields
        if self.entry_credit is None:
            self.entry_credit = self.premium_collected
        if self.open_date is None and self.entry_date:
            try:
                self.open_date = self.entry_date[:10]  # YYYY-MM-DD
            except (TypeError, IndexError):
                pass
        if self.realized_pnl is None:
            self.realized_pnl = 0.0
        if self.lifecycle_state is None:
            self.lifecycle_state = self.state if self.state else "OPEN"

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
        exit_plan: Optional["ExitPlan"] = None,
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
        exit_plan:
            Optional formal exit rules; if None, default CSP ExitPlan is used.
        """
        if exit_plan is None:
            from app.models.exit_plan import get_default_exit_plan
            exit_plan = get_default_exit_plan("CSP")
        now_iso = datetime.now(timezone.utc).isoformat()
        return Position(
            id=str(uuid4()),
            symbol=symbol.upper(),
            position_type="CSP",
            strike=float(strike),
            expiry=expiry,
            contracts=int(contracts),
            premium_collected=float(premium_collected),
            entry_date=now_iso,
            status="OPEN",
            state="NEW",  # New positions start in NEW state
            state_history=[],
            notes=notes,
            exit_plan=exit_plan,
            entry_credit=float(premium_collected),
            open_date=now_iso[:10],
            close_date=None,
            realized_pnl=0.0,
            lifecycle_state="OPEN",
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
        now_iso = datetime.now(timezone.utc).isoformat()
        return Position(
            id=str(uuid4()),
            symbol=symbol.upper(),
            position_type="SHARES",
            strike=None,
            expiry=None,
            contracts=int(shares),
            premium_collected=0.0,
            entry_date=now_iso,
            status="OPEN",
            state="NEW",
            state_history=[],
            notes=notes,
            entry_credit=0.0,
            open_date=now_iso[:10],
            close_date=None,
            realized_pnl=0.0,
            lifecycle_state="OPEN",
        )


__all__ = ["Position", "PositionType", "PositionStatus"]

