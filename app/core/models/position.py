#!/usr/bin/env python3
# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Position models used by the ChakraOps engine.

This module defines light-weight, typed containers for tracking positions.
It is intentionally free of business logic; higher-level orchestration
layers are responsible for decisions and state transitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4


PositionType = Literal["CSP", "SHARES"]
PositionStatus = Literal["OPEN", "ASSIGNED", "CLOSED"]


@dataclass(slots=True)
class Position:
    """Represents a single trading position.

    Fields are designed to be serialization-friendly (e.g. JSON/SQLite) and
    to capture the minimal information required to reason about CSP and
    share-only positions.
    """

    id: str
    symbol: str
    position_type: PositionType
    strike: Optional[float]
    expiry: Optional[str]  # ISO date YYYY-MM-DD
    contracts: int
    premium_collected: float
    entry_date: str        # ISO datetime
    status: PositionStatus
    notes: Optional[str] = None

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
            entry_date=datetime.utcnow().isoformat(),
            status="OPEN",
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
            entry_date=datetime.utcnow().isoformat(),
            status="OPEN",
            notes=notes,
        )


__all__ = ["Position", "PositionType", "PositionStatus"]

