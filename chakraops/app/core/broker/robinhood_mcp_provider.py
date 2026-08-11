# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 Robinhood MCP read provider — maps accounts to aliases; no balances hardcoded."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.broker.models import (
    ACCOUNT_ALIASES,
    BrokerAccount,
    BrokerBalances,
    BrokerOrderSummary,
    BrokerSnapshot,
    EquityPosition,
    OptionPosition,
    mask_account_number,
    utc_now_iso,
)
from app.core.broker.provider import BrokerReadProviderBase
from app.core.broker.robinhood_mcp_client import RobinhoodMcpClient

logger = logging.getLogger(__name__)

# Alias preference order for heuristic mapping (type/name only — never hardcoded balances).
_ALIAS_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("acct_ira_roth", ("roth", "ira_roth", "traditional_ira", "ira")),
    ("acct_agentic", ("agentic", "managed", "advisory")),
    ("acct_individual", ("individual", "brokerage", "cash", "margin", "joint")),
)


class RobinhoodMcpReadProvider(BrokerReadProviderBase):
    """BrokerReadProvider backed by Robinhood MCP read tools only."""

    def __init__(self, client: Optional[RobinhoodMcpClient] = None) -> None:
        self.client = client or RobinhoodMcpClient()
        # alias -> raw account_number (in-memory only; never logged in full)
        self._alias_to_number: Dict[str, str] = {}
        self._accounts_cache: List[BrokerAccount] = []

    def list_accounts(self) -> List[BrokerAccount]:
        result = self.client.call_tool("get_accounts", {})
        if not result.ok:
            logger.warning("get_accounts failed: %s", result.error)
            return list(self._accounts_cache)
        accounts, mapping = _map_accounts(result.data)
        self._alias_to_number = mapping
        self._accounts_cache = accounts
        return list(accounts)

    def get_account_balances(self, account_alias: str) -> BrokerBalances:
        acct_num = self._resolve_number(account_alias)
        result = self.client.call_tool("get_portfolio", {"account_number": acct_num})
        if not result.ok:
            raise RuntimeError(result.error or "get_portfolio failed")
        return _balances_from_portfolio(result.data)

    def get_equity_positions(self, account_alias: str) -> List[EquityPosition]:
        acct_num = self._resolve_number(account_alias)
        result = self.client.call_tool("get_equity_positions", {"account_number": acct_num})
        if not result.ok:
            raise RuntimeError(result.error or "get_equity_positions failed")
        return _parse_equity_positions(result.data)

    def get_option_positions(self, account_alias: str) -> List[OptionPosition]:
        acct_num = self._resolve_number(account_alias)
        result = self.client.call_tool(
            "get_option_positions",
            {"account_number": acct_num, "nonzero": True},
        )
        if not result.ok:
            raise RuntimeError(result.error or "get_option_positions failed")
        return _parse_option_positions(result.data)

    def get_equity_orders(self, account_alias: str) -> Optional[List[BrokerOrderSummary]]:
        acct_num = self._resolve_number(account_alias)
        result = self.client.call_tool("get_equity_orders", {"account_number": acct_num})
        if not result.ok:
            logger.warning("get_equity_orders optional failed: %s", result.error)
            return None
        return _parse_equity_orders(result.data)

    def sync_snapshot(self, account_alias: str) -> BrokerSnapshot:
        errors: List[str] = []
        alias = (account_alias or "").strip()
        if alias not in ACCOUNT_ALIASES and alias not in self._alias_to_number:
            # Ensure mapping exists.
            self.list_accounts()
        if alias not in self._alias_to_number and alias not in {a.alias for a in self._accounts_cache}:
            errors.append(f"unknown_account_alias:{alias}")
            return BrokerSnapshot(
                account_alias=alias,
                fetched_at=utc_now_iso(),
                freshness="missing",
                completeness="empty",
                errors=errors,
                stale=True,
            )

        balances = BrokerBalances()
        equities: List[EquityPosition] = []
        options: List[OptionPosition] = []
        orders: Optional[List[BrokerOrderSummary]] = None

        try:
            balances = self.get_account_balances(alias)
        except Exception as exc:
            errors.append(f"balances:{type(exc).__name__}")

        try:
            equities = self.get_equity_positions(alias)
        except Exception as exc:
            errors.append(f"equity_positions:{type(exc).__name__}")

        try:
            options = self.get_option_positions(alias)
        except Exception as exc:
            errors.append(f"option_positions:{type(exc).__name__}")

        try:
            orders = self.get_equity_orders(alias)
        except Exception as exc:
            errors.append(f"equity_orders:{type(exc).__name__}")

        completeness = "complete"
        if errors:
            completeness = "partial" if (equities or options or balances.cash is not None) else "empty"
        if not errors and not equities and not options and balances.cash is None:
            completeness = "empty"

        return BrokerSnapshot(
            account_alias=alias,
            fetched_at=utc_now_iso(),
            balances=balances,
            equity_positions=equities,
            option_positions=options,
            equity_orders=list(orders or []),
            freshness="fresh" if not errors else "partial",
            completeness=completeness,
            errors=errors,
            stale=bool(errors),
            source="robinhood_mcp",
        )

    def _resolve_number(self, account_alias: str) -> str:
        alias = (account_alias or "").strip()
        if alias not in self._alias_to_number:
            self.list_accounts()
        num = self._alias_to_number.get(alias)
        if not num:
            raise KeyError(f"No mapped account for alias={alias}")
        return num


def _map_accounts(data: Any) -> Tuple[List[BrokerAccount], Dict[str, str]]:
    rows = _as_list(data, keys=("accounts", "results", "data"))
    used: set[str] = set()
    mapping: Dict[str, str] = {}
    accounts: List[BrokerAccount] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        number = str(
            row.get("account_number")
            or row.get("accountNumber")
            or row.get("number")
            or row.get("id")
            or ""
        ).strip()
        if not number:
            continue
        acct_type = str(
            row.get("brokerage_account_type")
            or row.get("account_type")
            or row.get("type")
            or row.get("management_type")
            or ""
        )
        name = str(row.get("nickname") or row.get("name") or row.get("display_name") or "")
        agentic_allowed = bool(row.get("agentic_allowed"))
        is_default = bool(row.get("is_default"))
        alias = _choose_alias(acct_type, name, used, idx, agentic_allowed=agentic_allowed, is_default=is_default)
        used.add(alias)
        mapping[alias] = number
        accounts.append(
            BrokerAccount(
                alias=alias,
                account_type=acct_type or "unknown",
                masked_account_number=mask_account_number(number),
                display_name=name or alias,
                brokerage="robinhood",
                meta={
                    "mapped_from": "get_accounts",
                    "agentic_allowed": agentic_allowed,
                    "is_default": is_default,
                    "trading_type": str(row.get("type") or ""),
                },
            )
        )
    return accounts, mapping


def _choose_alias(
    acct_type: str,
    name: str,
    used: set[str],
    idx: int,
    *,
    agentic_allowed: bool = False,
    is_default: bool = False,
) -> str:
    # Prefer explicit agentic flag over nickname heuristics.
    if agentic_allowed and "acct_agentic" not in used:
        return "acct_agentic"
    if is_default and "acct_individual" not in used:
        # Default brokerage account maps to individual unless already taken.
        blob = f"{acct_type} {name}".lower()
        if "ira" not in blob and "roth" not in blob:
            return "acct_individual"
    blob = f"{acct_type} {name}".lower()
    for alias, needles in _ALIAS_RULES:
        if alias in used:
            continue
        if any(n in blob for n in needles):
            return alias
    for alias in ACCOUNT_ALIASES:
        if alias not in used:
            return alias
    return f"acct_other_{idx}"


def _balances_from_portfolio(data: Any) -> BrokerBalances:
    d = data if isinstance(data, dict) else {}
    # Robinhood MCP wraps payloads as {"data": {...}, "guide": "..."}.
    if "data" in d and isinstance(d["data"], dict) and not any(
        k in d for k in ("cash", "equity", "total_value", "buying_power")
    ):
        d = d["data"]
    if "portfolio" in d and isinstance(d["portfolio"], dict):
        d = d["portfolio"]
    # Common field name variants — do not invent balances.
    cash = _first_float(d, ("cash", "cash_balance", "equity_cash", "withdrawable_cash"))
    bp_raw = d.get("buying_power")
    if isinstance(bp_raw, dict):
        bp = _first_float(bp_raw, ("buying_power", "unleveraged_buying_power", "buyingPower"))
    else:
        bp = _first_float(d, ("buying_power", "buyingPower", "portfolio_cash", "cash_available"))
    equity = _first_float(d, ("equity", "equity_value", "total_equity", "account_value", "total_value"))
    mv = _first_float(d, ("market_value", "marketValue", "total_market_value", "equity_value", "equity"))
    present = [k for k in d.keys() if isinstance(k, str)]
    return BrokerBalances(
        cash=cash,
        buying_power=bp,
        equity=equity,
        market_value=mv,
        currency=str(d.get("currency") or "USD"),
        raw_keys_present=present[:40],
    )


def _parse_equity_positions(data: Any) -> List[EquityPosition]:
    rows = _as_list(data, keys=("results", "positions", "equity_positions", "data"))
    out: List[EquityPosition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("instrument_symbol") or "").upper()
        if not symbol:
            continue
        qty = _first_float(row, ("quantity", "qty", "shares", "total_quantity")) or 0.0
        out.append(
            EquityPosition(
                symbol=symbol,
                quantity=qty,
                average_cost=_first_float(row, ("average_cost", "average_buy_price", "avg_cost")),
                market_value=_first_float(row, ("market_value", "marketValue")),
                side=str(row.get("side") or ("short" if qty < 0 else "long")),
            )
        )
    return out


def _parse_option_positions(data: Any) -> List[OptionPosition]:
    rows = _as_list(data, keys=("results", "positions", "option_positions", "data"))
    out: List[OptionPosition] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(
            row.get("symbol")
            or row.get("chain_symbol")
            or row.get("underlying")
            or ""
        ).upper()
        qty = _first_float(row, ("quantity", "qty", "total_quantity")) or 0.0
        opt_type = str(row.get("option_type") or row.get("type") or row.get("put_call") or "").lower()
        if opt_type not in {"call", "put"}:
            opt_type = "put" if "put" in opt_type else ("call" if "call" in opt_type else "unknown")
        out.append(
            OptionPosition(
                symbol=symbol or "UNKNOWN",
                option_type=opt_type,
                strike=_first_float(row, ("strike", "strike_price")),
                expiration=str(row.get("expiration") or row.get("expiration_date") or ""),
                quantity=qty,
                average_cost=_first_float(row, ("average_cost", "average_open_price", "average_price", "avg_cost")),
                side=str(row.get("type") or row.get("side") or ("short" if qty < 0 else "long")),
            )
        )
    return out


def _parse_equity_orders(data: Any) -> List[BrokerOrderSummary]:
    rows = _as_list(data, keys=("orders", "results", "data"))
    out: List[BrokerOrderSummary] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            BrokerOrderSummary(
                order_id=str(row.get("id") or row.get("order_id") or ""),
                symbol=str(row.get("symbol") or "").upper(),
                state=str(row.get("state") or ""),
                side=str(row.get("side") or ""),
                quantity=_first_float(row, ("quantity", "qty")),
                created_at=str(row.get("created_at") or row.get("updated_at") or ""),
            )
        )
    return out


def _as_list(data: Any, keys: Tuple[str, ...]) -> List[Any]:
    """Extract a list payload from MCP tool responses.

    Handles current Robinhood MCP envelopes like::
      {"data": {"accounts": [...]}, "guide": "..."}
      {"data": {"positions": [...]}, "guide": "..."}
    """
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in keys:
            v = data.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                # Nested envelope: data -> {accounts|positions|...}
                nested = _as_list(v, keys)
                if nested:
                    return nested
        # Single account/position object
        if any(k in data for k in ("account_number", "symbol", "quantity")):
            return [data]
    return []


def _first_float(d: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[float]:
    for k in keys:
        if k not in d:
            continue
        v = d.get(k)
        if v is None or v == "":
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None
