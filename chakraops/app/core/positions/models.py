# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Position model — tracked manually executed trades.

A Position represents a trade the user has manually executed outside ChakraOps.
ChakraOps NEVER places trades. The Execute button creates a Position record
that tracks the user's intention to execute and their manual confirmation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Valid status values
VALID_STATUSES = {"OPEN", "PARTIAL_EXIT", "CLOSED", "ABORTED"}
VALID_STRATEGIES = {"CSP", "CC", "STOCK"}


@dataclass
class Position:
    """Manually tracked position.

    Fields:
        position_id: Unique identifier.
        account_id: Account this position belongs to.
        symbol: Ticker symbol (e.g. AAPL).
        strategy: CSP | CC | STOCK.
        contracts: Number of option contracts.
        strike: Option strike price (null for STOCK).
        expiration: Option expiration date YYYY-MM-DD (null for STOCK).
        credit_expected: Expected credit per contract (null for STOCK).
        quantity: Number of shares (for STOCK strategy).
        status: OPEN | PARTIAL_EXIT | CLOSED.
        opened_at: ISO datetime when position was opened.
        closed_at: ISO datetime when position was closed (null if open).
        notes: User notes about the position.
    """
    position_id: str
    account_id: str
    symbol: str
    strategy: str
    contracts: int = 0
    strike: Optional[float] = None
    expiration: Optional[str] = None
    credit_expected: Optional[float] = None
    quantity: Optional[int] = None
    status: str = "OPEN"
    opened_at: str = ""
    closed_at: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.opened_at:
            self.opened_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "contracts": self.contracts,
            "strike": self.strike,
            "expiration": self.expiration,
            "credit_expected": self.credit_expected,
            "quantity": self.quantity,
            "status": self.status,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Position":
        return cls(
            position_id=d["position_id"],
            account_id=d.get("account_id", ""),
            symbol=d.get("symbol", ""),
            strategy=d.get("strategy", "CSP"),
            contracts=int(d.get("contracts", 0)),
            strike=d.get("strike"),
            expiration=d.get("expiration"),
            credit_expected=d.get("credit_expected"),
            quantity=d.get("quantity"),
            status=d.get("status", "OPEN"),
            opened_at=d.get("opened_at", ""),
            closed_at=d.get("closed_at"),
            notes=d.get("notes", ""),
        )


def generate_position_id() -> str:
    """Generate a unique position ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"pos_{ts}_{short}"
