# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Account model — capital awareness and position sizing foundation.

An Account represents a brokerage account with capital limits and strategy constraints.
ChakraOps never places trades; accounts exist to inform position sizing and recommendations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# Valid provider and account type values
VALID_PROVIDERS = {"Robinhood", "Schwab", "Fidelity", "Manual"}
VALID_ACCOUNT_TYPES = {"Taxable", "Roth", "IRA", "401k"}
VALID_STRATEGIES = {"CSP", "CC", "STOCK"}


@dataclass
class Account:
    """Brokerage account for capital-aware trade management.

    Fields:
        account_id: Unique, user-defined identifier.
        provider: Brokerage provider (Robinhood, Schwab, Fidelity, Manual).
        account_type: Account type (Taxable, Roth, IRA, 401k).
        total_capital: Total capital in USD (must be > 0).
        max_capital_per_trade_pct: Max % of capital per trade (1-100).
        max_total_exposure_pct: Max % of total exposure allowed (1-100).
        allowed_strategies: List of allowed strategy types (CSP, CC, STOCK).
        is_default: Whether this is the default account (only one allowed).
        created_at: ISO datetime when account was created.
        updated_at: ISO datetime when account was last updated.
        active: Whether this account is active.
        Phase 11.0 sizing (optional, for guardrails):
        max_collateral_per_trade: Max $ collateral per trade (None = no limit).
        max_total_collateral: Max $ total open collateral (None = no limit).
        max_positions_open: Max number of open positions (None = no limit).
        min_credit_per_contract: Min $ credit per contract (None = no limit).
    """
    account_id: str
    provider: str
    account_type: str
    total_capital: float
    max_capital_per_trade_pct: float
    max_total_exposure_pct: float
    allowed_strategies: List[str]
    is_default: bool = False
    created_at: str = ""
    updated_at: str = ""
    active: bool = True
    # Phase 11.0: Account-based sizing guardrails (optional)
    max_collateral_per_trade: Optional[float] = None
    max_total_collateral: Optional[float] = None
    max_positions_open: Optional[int] = None
    min_credit_per_contract: Optional[float] = None

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "account_id": self.account_id,
            "provider": self.provider,
            "account_type": self.account_type,
            "total_capital": self.total_capital,
            "max_capital_per_trade_pct": self.max_capital_per_trade_pct,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "allowed_strategies": self.allowed_strategies,
            "is_default": self.is_default,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active": self.active,
        }
        for key in ("max_collateral_per_trade", "max_total_collateral", "max_positions_open", "min_credit_per_contract"):
            v = getattr(self, key, None)
            if v is not None:
                d[key] = v
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Account":
        mcp = d.get("max_collateral_per_trade")
        mtc = d.get("max_total_collateral")
        mpo = d.get("max_positions_open")
        mcc = d.get("min_credit_per_contract")
        return cls(
            account_id=d["account_id"],
            provider=d.get("provider", "Manual"),
            account_type=d.get("account_type", "Taxable"),
            total_capital=float(d.get("total_capital", 0)),
            max_capital_per_trade_pct=float(d.get("max_capital_per_trade_pct", 5)),
            max_total_exposure_pct=float(d.get("max_total_exposure_pct", 30)),
            allowed_strategies=list(d.get("allowed_strategies", ["CSP"])),
            is_default=bool(d.get("is_default", False)),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            active=bool(d.get("active", True)),
            max_collateral_per_trade=float(mcp) if mcp is not None else None,
            max_total_collateral=float(mtc) if mtc is not None else None,
            max_positions_open=int(mpo) if mpo is not None else None,
            min_credit_per_contract=float(mcc) if mcc is not None else None,
        )


def generate_account_id() -> str:
    """Generate a unique account ID."""
    return f"acct_{uuid.uuid4().hex[:12]}"
