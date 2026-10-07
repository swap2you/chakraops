# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Trade Journal data models: Trade, Fill, and derived fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class FillAction(str, Enum):
    OPEN = "OPEN"
    CLOSE = "CLOSE"


@dataclass
class Fill:
    """Execution fill: open or close, with qty, price, fees."""
    fill_id: str
    trade_id: str
    filled_at: str  # ISO datetime
    action: FillAction  # OPEN or CLOSE
    qty: int  # contracts
    price: float
    fees: float = 0.0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "trade_id": self.trade_id,
            "filled_at": self.filled_at,
            "action": self.action.value,
            "qty": self.qty,
            "price": self.price,
            "fees": self.fees,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Fill":
        return cls(
            fill_id=d["fill_id"],
            trade_id=d["trade_id"],
            filled_at=d["filled_at"],
            action=FillAction(d.get("action", "OPEN")),
            qty=int(d["qty"]),
            price=float(d["price"]),
            fees=float(d.get("fees", 0)),
            tags=list(d.get("tags", [])),
        )


@dataclass
class Trade:
    """Journal trade: symbol, strategy, terms, optional stop/target."""
    trade_id: str
    symbol: str
    strategy: str  # CSP, CC, etc.
    opened_at: str  # ISO datetime
    expiry: Optional[str] = None  # YYYY-MM-DD
    strike: Optional[float] = None
    side: str = "SELL"  # SELL for open, BUY for close
    contracts: int = 0  # initial contracts
    entry_mid_est: Optional[float] = None
    run_id: Optional[str] = None  # evaluation run reference
    notes: Optional[str] = None
    stop_level: Optional[float] = None
    target_levels: List[float] = field(default_factory=list)  # e.g. [0.5, 0.25] for 50%, 25% profit
    fills: List[Fill] = field(default_factory=list)
    
    # Derived (computed by store)
    remaining_qty: int = 0
    avg_entry: Optional[float] = None
    avg_exit: Optional[float] = None
    realized_pnl: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "opened_at": self.opened_at,
            "expiry": self.expiry,
            "strike": self.strike,
            "side": self.side,
            "contracts": self.contracts,
            "entry_mid_est": self.entry_mid_est,
            "run_id": self.run_id,
            "notes": self.notes,
            "stop_level": self.stop_level,
            "target_levels": self.target_levels,
            "fills": [f.to_dict() for f in self.fills],
            "remaining_qty": self.remaining_qty,
            "avg_entry": self.avg_entry,
            "avg_exit": self.avg_exit,
            "realized_pnl": self.realized_pnl,
        }
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trade":
        fills = [Fill.from_dict(f) for f in d.get("fills", [])]
        return cls(
            trade_id=d["trade_id"],
            symbol=d["symbol"],
            strategy=d["strategy"],
            opened_at=d["opened_at"],
            expiry=d.get("expiry"),
            strike=d.get("strike"),
            side=d.get("side", "SELL"),
            contracts=int(d.get("contracts", 0)),
            entry_mid_est=d.get("entry_mid_est"),
            run_id=d.get("run_id"),
            notes=d.get("notes"),
            stop_level=d.get("stop_level"),
            target_levels=list(d.get("target_levels", [])),
            fills=fills,
            remaining_qty=int(d.get("remaining_qty", 0)),
            avg_entry=d.get("avg_entry"),
            avg_exit=d.get("avg_exit"),
            realized_pnl=d.get("realized_pnl"),
        )


def generate_trade_id() -> str:
    """Generate a unique trade ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"trade_{ts}_{short}"


def generate_fill_id() -> str:
    """Generate a unique fill ID."""
    return f"fill_{uuid.uuid4().hex[:12]}"
