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
VALID_OPTION_TYPES = {"PUT", "CALL"}


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
    # Phase 4: Entry decision snapshot (optional, attached to position)
    band: Optional[str] = None  # A | B | C | D
    risk_flags_at_entry: Optional[List[str]] = None
    portfolio_utilization_pct: Optional[float] = None
    sector_exposure_pct: Optional[float] = None
    thesis_strength: Optional[int] = None  # 1-5
    data_sufficiency: Optional[str] = None  # PASS | WARN | FAIL
    # Phase 5: Explicit risk unit (1R in dollars). Required for return_on_risk; if missing, R = UNKNOWN.
    risk_amount_at_entry: Optional[float] = None
    # Phase 5: Manual override for data_sufficiency; logged distinctly from auto-derived
    data_sufficiency_override: Optional[str] = None  # PASS | WARN | FAIL
    data_sufficiency_override_source: Optional[str] = None  # "MANUAL" when user overrides
    # Phase 7.2: Trade lifecycle — exit levels and stop
    stop_price: Optional[float] = None
    t1: Optional[float] = None
    t2: Optional[float] = None
    t3: Optional[float] = None

    # Phase 10.0: Portfolio completion fields
    id: Optional[str] = None  # Alias for position_id (uuid); set from position_id if missing
    underlying: Optional[str] = None  # Same as symbol
    option_type: Optional[str] = None  # PUT | CALL
    open_credit: Optional[float] = None  # Credit received at open
    # Phase 11.0: Contract identity and decision reference
    option_symbol: Optional[str] = None  # OCC option symbol
    contract_key: Optional[str] = None  # Derived key (strike-expiry-type)
    decision_ref: Optional[Dict[str, Any]] = None  # evaluation_timestamp_utc, artifact_source, selected_contract_key
    open_price: Optional[float] = None
    open_fees: Optional[float] = None
    open_time_utc: Optional[str] = None
    close_debit: Optional[float] = None  # Debit paid at close
    close_price: Optional[float] = None
    close_fees: Optional[float] = None
    close_time_utc: Optional[str] = None
    collateral: Optional[float] = None  # For CSP: strike*100*contracts
    realized_pnl: Optional[float] = None
    is_test: bool = False  # DIAG_TEST or user-created test data
    created_at_utc: Optional[str] = None
    updated_at_utc: Optional[str] = None

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.opened_at:
            self.opened_at = now
        if self.id is None:
            self.id = self.position_id
        if self.underlying is None and self.symbol:
            self.underlying = self.symbol
        if self.open_time_utc is None and self.opened_at:
            self.open_time_utc = self.opened_at
        if self.open_credit is None and self.credit_expected is not None:
            self.open_credit = self.credit_expected
        if self.created_at_utc is None:
            self.created_at_utc = self.opened_at or now
        if self.updated_at_utc is None:
            self.updated_at_utc = self.opened_at or now
        # Phase 10.0: Compute collateral for CSP/CC if not set
        if self.collateral is None and (self.strategy or "").upper() in ("CSP", "CC") and self.strike and self.contracts:
            self.collateral = float(self.strike) * 100 * int(self.contracts)
        # Mark DIAG_TEST positions as test
        if not self.is_test and (self.symbol or "").strip().upper().startswith("DIAG_TEST"):
            self.is_test = True

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
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
        # Phase 4/5: Entry snapshot (only if present)
        for key in ("band", "risk_flags_at_entry", "portfolio_utilization_pct",
                    "sector_exposure_pct", "thesis_strength", "data_sufficiency",
                    "risk_amount_at_entry", "data_sufficiency_override", "data_sufficiency_override_source"):
            v = getattr(self, key, None)
            if v is not None:
                d[key] = v
        # Phase 7.2: Lifecycle
        for key in ("stop_price", "t1", "t2", "t3"):
            v = getattr(self, key, None)
            if v is not None:
                d[key] = v
        # Phase 10.0
        for key in ("id", "underlying", "option_type", "open_credit", "open_price", "open_fees",
                    "open_time_utc", "close_debit", "close_price", "close_fees", "close_time_utc",
                    "collateral", "realized_pnl", "is_test", "created_at_utc", "updated_at_utc",
                    "option_symbol", "contract_key", "decision_ref"):
            v = getattr(self, key, None)
            if v is not None or key == "is_test":
                d[key] = v
        d["entry_credit"] = self.credit_expected
        d["entry_date"] = self.opened_at
        d["expiry"] = self.expiration
        return d

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
            credit_expected=d.get("credit_expected") or d.get("entry_credit"),
            quantity=d.get("quantity"),
            status=d.get("status", "OPEN"),
            opened_at=d.get("opened_at", ""),
            closed_at=d.get("closed_at"),
            notes=d.get("notes", ""),
            band=d.get("band"),
            risk_flags_at_entry=d.get("risk_flags_at_entry"),
            portfolio_utilization_pct=d.get("portfolio_utilization_pct"),
            sector_exposure_pct=d.get("sector_exposure_pct"),
            thesis_strength=d.get("thesis_strength"),
            data_sufficiency=d.get("data_sufficiency"),
            risk_amount_at_entry=d.get("risk_amount_at_entry"),
            data_sufficiency_override=d.get("data_sufficiency_override"),
            data_sufficiency_override_source=d.get("data_sufficiency_override_source"),
            stop_price=d.get("stop_price"),
            t1=d.get("t1"),
            t2=d.get("t2"),
            t3=d.get("t3"),
            id=d.get("id") or d.get("position_id"),
            underlying=d.get("underlying") or d.get("symbol"),
            option_type=d.get("option_type"),
            option_symbol=d.get("option_symbol"),
            contract_key=d.get("contract_key"),
            decision_ref=d.get("decision_ref"),
            open_credit=d.get("open_credit") or d.get("credit_expected") or d.get("entry_credit"),
            open_price=d.get("open_price"),
            open_fees=d.get("open_fees"),
            open_time_utc=d.get("open_time_utc") or d.get("opened_at"),
            close_debit=d.get("close_debit"),
            close_price=d.get("close_price"),
            close_fees=d.get("close_fees"),
            close_time_utc=d.get("close_time_utc") or d.get("closed_at"),
            collateral=d.get("collateral"),
            realized_pnl=d.get("realized_pnl"),
            is_test=bool(d.get("is_test", False)),
            created_at_utc=d.get("created_at_utc") or d.get("opened_at"),
            updated_at_utc=d.get("updated_at_utc") or d.get("opened_at"),
        )


def generate_position_id() -> str:
    """Generate a unique position ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:8]
    return f"pos_{ts}_{short}"
