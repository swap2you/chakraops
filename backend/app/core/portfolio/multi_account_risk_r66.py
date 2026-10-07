# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R66 account-aware portfolio risk — no cross-account collateral pooling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from app.core.broker.models import (
    ACCOUNT_ALIASES,
    BrokerBalances,
    BrokerSnapshot,
    EquityPosition,
    OptionPosition,
)

# Account roles that must never share collateral / buying power.
ISOLATED_ACCOUNT_ROLES = frozenset(
    {
        "taxable",
        "individual",
        "margin",
        "roth",
        "ira",
        "ira_roth",
        "agentic",
        "acct_individual",
        "acct_ira_roth",
        "acct_agentic",
    }
)

ROLE_BY_ALIAS = {
    "acct_individual": "taxable",
    "acct_ira_roth": "roth",
    "acct_agentic": "agentic",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _role_for_alias(alias: str, account_type: str = "") -> str:
    a = (alias or "").strip().lower()
    if a in ROLE_BY_ALIAS:
        return ROLE_BY_ALIAS[a]
    t = (account_type or "").strip().lower()
    if "agentic" in t or a == "acct_agentic":
        return "agentic"
    if "roth" in t or "ira" in t:
        return "roth"
    if "margin" in t or "individual" in t or "taxable" in t:
        return "taxable"
    return a or "unknown"


def _equity_notional(pos: EquityPosition) -> float:
    if pos.market_value is not None:
        try:
            return abs(float(pos.market_value))
        except (TypeError, ValueError):
            pass
    qty = abs(float(pos.quantity or 0.0))
    cost = float(pos.average_cost or 0.0)
    return qty * cost


def _option_notional(pos: OptionPosition) -> float:
    strike = float(pos.strike or 0.0)
    qty = abs(float(pos.quantity or 0.0))
    return strike * 100.0 * qty


def _csp_assignment_exposure(options: Iterable[OptionPosition]) -> float:
    total = 0.0
    for op in options:
        if (op.option_type or "").lower() != "put":
            continue
        if (op.side or "").lower() != "short":
            continue
        total += _option_notional(op)
    return total


def _cc_call_away_exposure(options: Iterable[OptionPosition]) -> float:
    total = 0.0
    for op in options:
        if (op.option_type or "").lower() != "call":
            continue
        if (op.side or "").lower() != "short":
            continue
        total += _option_notional(op)
    return total


def evaluate_account_risk_slice(
    *,
    account_alias: str,
    account_type: str = "",
    balances: Optional[BrokerBalances] = None,
    equities: Optional[List[EquityPosition]] = None,
    options: Optional[List[OptionPosition]] = None,
    stale: bool = False,
) -> Dict[str, Any]:
    """Compute risk metrics for a single account. Never pools other accounts."""
    balances = balances or BrokerBalances()
    equities = list(equities or [])
    options = list(options or [])
    role = _role_for_alias(account_alias, account_type)

    symbol_exposure: Dict[str, float] = {}
    for eq in equities:
        sym = (eq.symbol or "").upper()
        if not sym:
            continue
        symbol_exposure[sym] = symbol_exposure.get(sym, 0.0) + _equity_notional(eq)
    for op in options:
        und = (op.symbol or "").upper()
        if not und:
            continue
        symbol_exposure[und] = symbol_exposure.get(und, 0.0) + _option_notional(op)

    equity_notional = sum(_equity_notional(e) for e in equities)
    options_notional = sum(_option_notional(o) for o in options)
    cash = float(balances.cash) if balances.cash is not None else None
    buying_power = float(balances.buying_power) if balances.buying_power is not None else None
    equity = float(balances.equity) if balances.equity is not None else None

    csp_exposure = _csp_assignment_exposure(options)
    cc_exposure = _cc_call_away_exposure(options)

    collateral_util = None
    if cash is not None and cash > 0 and csp_exposure > 0:
        collateral_util = min(csp_exposure / cash, 99.0)

    concentration = None
    denom = equity if equity and equity > 0 else (equity_notional + options_notional)
    if denom and denom > 0 and symbol_exposure:
        top = max(symbol_exposure.values())
        concentration = top / denom

    expirations = sorted({(o.expiration or "").strip() for o in options if (o.expiration or "").strip()})

    return {
        "account_alias": account_alias,
        "account_role": role,
        "account_type": account_type,
        "isolated": True,
        "pooling_allowed": False,
        "stale": bool(stale),
        "balances": {
            "cash": cash,
            "buying_power": buying_power,
            "equity": equity,
            "market_value": float(balances.market_value) if balances.market_value is not None else None,
        },
        "metrics": {
            "symbol_exposure": symbol_exposure,
            "equity_notional": equity_notional,
            "options_notional": options_notional,
            "csp_assignment_exposure": csp_exposure,
            "cc_call_away_exposure": cc_exposure,
            "collateral_utilization": collateral_util,
            "concentration": concentration,
            "expirations": expirations,
            "open_equity_count": len(equities),
            "open_option_count": len(options),
        },
        "notes": [
            "Buying power and collateral are scoped to this account only.",
            "Agentic account is isolated and never used for execution.",
        ],
        "manual_only": True,
        "trade_execution": False,
    }


def evaluate_multi_account_risk(
    snapshots: Mapping[str, BrokerSnapshot] | Iterable[BrokerSnapshot],
    *,
    account_meta: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build per-account risk slices. Explicitly refuses pooled collateral totals."""
    if isinstance(snapshots, Mapping):
        snap_list = list(snapshots.values())
    else:
        snap_list = list(snapshots)

    meta = account_meta or {}
    accounts: List[Dict[str, Any]] = []
    for snap in snap_list:
        alias = snap.account_alias
        m = meta.get(alias) or {}
        accounts.append(
            evaluate_account_risk_slice(
                account_alias=alias,
                account_type=str(m.get("account_type") or ""),
                balances=snap.balances,
                equities=snap.equity_positions,
                options=snap.option_positions,
                stale=bool(snap.stale),
            )
        )

    # Honesty: never sum cash/buying_power across taxable + Roth + Agentic.
    pooled_refused = {
        "pooled_cash": None,
        "pooled_buying_power": None,
        "pooled_collateral": None,
        "reason": "cross_account_collateral_pooling_refused",
        "detail": "Taxable, Roth/IRA, and Agentic buying power/collateral are never combined.",
    }

    roles_present = sorted({a["account_role"] for a in accounts})
    return {
        "schema": "portfolio_risk_v66",
        "as_of": _utc_now_iso(),
        "accounts": accounts,
        "roles_present": roles_present,
        "known_aliases": list(ACCOUNT_ALIASES),
        "pooled_totals": pooled_refused,
        "cross_account_leakage": False,
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "provider_abstraction": "BrokerReadProvider",
    }


def assert_no_cross_account_leakage(result: Dict[str, Any]) -> bool:
    """Test helper: pooled totals must be null and each slice isolated."""
    pooled = result.get("pooled_totals") or {}
    if pooled.get("pooled_cash") is not None:
        return False
    if pooled.get("pooled_buying_power") is not None:
        return False
    if pooled.get("pooled_collateral") is not None:
        return False
    for acct in result.get("accounts") or []:
        if not acct.get("isolated"):
            return False
        if acct.get("pooling_allowed"):
            return False
    return result.get("cross_account_leakage") is False
