# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Capital ledger and outcome accounting (Phase 6.4).

Tracks capital movement precisely: OPEN (credit inflow), PARTIAL_CLOSE (realized pnl),
CLOSE (final reconciliation), ASSIGNMENT (capital adjustment). Enables reproducible
monthly summaries and trust report integration.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class CapitalLedgerEventType(str, Enum):
    """Ledger event type: maps to position lifecycle and cash impact."""

    OPEN = "OPEN"                     # Credit inflow at open
    PARTIAL_CLOSE = "PARTIAL_CLOSE"   # Realized pnl on partial close
    CLOSE = "CLOSE"                   # Final reconciliation at close
    ASSIGNMENT = "ASSIGNMENT"         # Capital adjustment on assignment


@dataclass
class CapitalLedgerEntry:
    """A single capital ledger row: date, position, event type, cash delta, notes."""

    date: str           # YYYY-MM-DD
    position_id: str
    event_type: str     # CapitalLedgerEventType value
    cash_delta: float   # Positive = inflow, negative = outflow
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        self.cash_delta = float(self.cash_delta)


@dataclass
class MonthlySummary:
    """Reproducible monthly outcome summary from ledger + positions."""

    year: int
    month: int
    total_credit_collected: float
    realized_pnl: float
    unrealized_pnl: float
    win_rate: float       # 0.0–1.0
    avg_days_in_trade: float
    max_drawdown: float   # Simple peak-to-trough

    def __post_init__(self) -> None:
        self.total_credit_collected = float(self.total_credit_collected)
        self.realized_pnl = float(self.realized_pnl)
        self.unrealized_pnl = float(self.unrealized_pnl)
        self.win_rate = float(self.win_rate)
        self.avg_days_in_trade = float(self.avg_days_in_trade)
        self.max_drawdown = float(self.max_drawdown)


__all__ = [
    "CapitalLedgerEventType",
    "CapitalLedgerEntry",
    "MonthlySummary",
]
