# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 normalized broker read models (masked account numbers; no secrets)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "r52.1"

# Stable aliases used across ChakraOps — never persist full account numbers as keys.
ACCOUNT_ALIASES = (
    "acct_individual",
    "acct_ira_roth",
    "acct_agentic",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mask_account_number(account_number: Optional[str], *, visible_tail: int = 4) -> str:
    """Mask an account number for logs/API/evidence. Never returns the full value."""
    raw = (account_number or "").strip()
    if not raw:
        return "****"
    if len(raw) <= visible_tail:
        return "*" * len(raw)
    return ("*" * max(4, len(raw) - visible_tail)) + raw[-visible_tail:]


def redact_account_fields(payload: Any) -> Any:
    """Recursively mask common account-number field names in nested dict/list structures."""
    sensitive_keys = {
        "account_number",
        "account_numbers",
        "account_id",
        "brokerage_account_number",
        "acct_number",
    }
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for k, v in payload.items():
            key_l = str(k).lower()
            if key_l in sensitive_keys:
                if isinstance(v, list):
                    out[k] = [mask_account_number(str(x)) if x is not None else x for x in v]
                else:
                    out[k] = mask_account_number(str(v) if v is not None else "")
            else:
                out[k] = redact_account_fields(v)
        return out
    if isinstance(payload, list):
        return [redact_account_fields(x) for x in payload]
    return payload


@dataclass
class BrokerAccount:
    alias: str
    account_type: str = ""
    masked_account_number: str = "****"
    display_name: str = ""
    brokerage: str = "robinhood"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrokerAccount":
        return cls(
            alias=str(d.get("alias") or ""),
            account_type=str(d.get("account_type") or ""),
            masked_account_number=str(d.get("masked_account_number") or "****"),
            display_name=str(d.get("display_name") or ""),
            brokerage=str(d.get("brokerage") or "robinhood"),
            meta=dict(d.get("meta") or {}),
        )


@dataclass
class BrokerBalances:
    cash: Optional[float] = None
    buying_power: Optional[float] = None
    equity: Optional[float] = None
    market_value: Optional[float] = None
    currency: str = "USD"
    raw_keys_present: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrokerBalances":
        def _f(key: str) -> Optional[float]:
            v = d.get(key)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return cls(
            cash=_f("cash"),
            buying_power=_f("buying_power"),
            equity=_f("equity"),
            market_value=_f("market_value"),
            currency=str(d.get("currency") or "USD"),
            raw_keys_present=list(d.get("raw_keys_present") or []),
        )

    def looks_like_zero_wipe(self) -> bool:
        """True when all numeric balances are present and exactly 0 (suspicious wipe)."""
        nums = [self.cash, self.buying_power, self.equity, self.market_value]
        present = [n for n in nums if n is not None]
        return bool(present) and all(n == 0.0 for n in present)


@dataclass
class EquityPosition:
    symbol: str
    quantity: float
    average_cost: Optional[float] = None
    market_value: Optional[float] = None
    side: str = "long"
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EquityPosition":
        return cls(
            symbol=str(d.get("symbol") or "").upper(),
            quantity=float(d.get("quantity") or 0.0),
            average_cost=_opt_float(d.get("average_cost")),
            market_value=_opt_float(d.get("market_value")),
            side=str(d.get("side") or "long"),
            meta=dict(d.get("meta") or {}),
        )


@dataclass
class OptionPosition:
    symbol: str
    option_type: str  # call|put
    strike: Optional[float] = None
    expiration: str = ""
    quantity: float = 0.0
    average_cost: Optional[float] = None
    side: str = "long"  # long|short
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OptionPosition":
        return cls(
            symbol=str(d.get("symbol") or "").upper(),
            option_type=str(d.get("option_type") or "").lower(),
            strike=_opt_float(d.get("strike")),
            expiration=str(d.get("expiration") or ""),
            quantity=float(d.get("quantity") or 0.0),
            average_cost=_opt_float(d.get("average_cost")),
            side=str(d.get("side") or "long"),
            meta=dict(d.get("meta") or {}),
        )


@dataclass
class BrokerOrderSummary:
    order_id: str = ""
    symbol: str = ""
    state: str = ""
    side: str = ""
    quantity: Optional[float] = None
    created_at: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrokerOrderSummary":
        return cls(
            order_id=str(d.get("order_id") or ""),
            symbol=str(d.get("symbol") or "").upper(),
            state=str(d.get("state") or ""),
            side=str(d.get("side") or ""),
            quantity=_opt_float(d.get("quantity")),
            created_at=str(d.get("created_at") or ""),
            meta=dict(d.get("meta") or {}),
        )


@dataclass
class BrokerSnapshot:
    account_alias: str
    fetched_at: str
    balances: BrokerBalances = field(default_factory=BrokerBalances)
    equity_positions: List[EquityPosition] = field(default_factory=list)
    option_positions: List[OptionPosition] = field(default_factory=list)
    equity_orders: List[BrokerOrderSummary] = field(default_factory=list)
    freshness: str = "unknown"  # fresh|stale|missing
    completeness: str = "unknown"  # complete|partial|empty
    errors: List[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    source: str = "robinhood_mcp"
    stale: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_alias": self.account_alias,
            "fetched_at": self.fetched_at,
            "balances": self.balances.to_dict(),
            "equity_positions": [p.to_dict() for p in self.equity_positions],
            "option_positions": [p.to_dict() for p in self.option_positions],
            "equity_orders": [o.to_dict() for o in self.equity_orders],
            "freshness": self.freshness,
            "completeness": self.completeness,
            "errors": list(self.errors),
            "schema_version": self.schema_version,
            "source": self.source,
            "stale": self.stale,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BrokerSnapshot":
        return cls(
            account_alias=str(d.get("account_alias") or ""),
            fetched_at=str(d.get("fetched_at") or ""),
            balances=BrokerBalances.from_dict(dict(d.get("balances") or {})),
            equity_positions=[EquityPosition.from_dict(x) for x in (d.get("equity_positions") or [])],
            option_positions=[OptionPosition.from_dict(x) for x in (d.get("option_positions") or [])],
            equity_orders=[BrokerOrderSummary.from_dict(x) for x in (d.get("equity_orders") or [])],
            freshness=str(d.get("freshness") or "unknown"),
            completeness=str(d.get("completeness") or "unknown"),
            errors=list(d.get("errors") or []),
            schema_version=str(d.get("schema_version") or SCHEMA_VERSION),
            source=str(d.get("source") or "robinhood_mcp"),
            stale=bool(d.get("stale")),
        )

    def masked_for_api(self) -> Dict[str, Any]:
        """API-safe dict (aliases only; no full account numbers)."""
        return redact_account_fields(self.to_dict())


def _opt_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
