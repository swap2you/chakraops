# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R66 account-aware risk — no cross-account collateral pooling."""

from __future__ import annotations

from typing import Any, Dict, List


ACCOUNT_BUCKETS = ("acct_individual", "acct_ira_roth", "acct_agentic")


def compute_account_risk(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute per-account exposure; never pool IRA with taxable collateral."""
    by_alias: Dict[str, Dict[str, Any]] = {}
    for row in accounts or []:
        if not isinstance(row, dict):
            continue
        alias = str(row.get("alias") or "").strip()
        if not alias:
            continue
        cash = float(row.get("cash") or 0.0)
        equity = float(row.get("equity") or row.get("market_value") or 0.0)
        bp = float(row.get("buying_power") or 0.0)
        by_alias[alias] = {
            "alias": alias,
            "cash": cash,
            "equity": equity,
            "buying_power": bp,
            "csp_collateral_budget": cash if alias != "acct_agentic" else 0.0,
            "notes": "Agentic excluded from execution collateral" if alias == "acct_agentic" else "",
        }

    # Explicit isolation: taxable BP must not include IRA cash.
    taxable = by_alias.get("acct_individual", {})
    ira = by_alias.get("acct_ira_roth", {})
    leakage = False
    if taxable and ira:
        # Detect mistaken pooling if caller passed combined cash into taxable.
        if taxable.get("cash") == (float(taxable.get("cash") or 0) + float(ira.get("cash") or 0)) and float(ira.get("cash") or 0) > 0:
            leakage = True

    return {
        "manual_only": True,
        "trade_execution": False,
        "accounts": by_alias,
        "cross_account_collateral_pooling": False,
        "leakage_detected": leakage,
        "agentic_execution": False,
        "message": "Account boundaries enforced; IRA cash is not taxable CSP collateral.",
    }


def hedge_scenario(
    *,
    portfolio_equity: float,
    hedge_pct: float = 0.1,
    put_cost_pct: float = 0.02,
) -> Dict[str, Any]:
    """Advisory hedge cost/coverage scenario — no execution."""
    eq = max(0.0, float(portfolio_equity or 0.0))
    hp = min(max(float(hedge_pct), 0.0), 1.0)
    cost = eq * hp * max(float(put_cost_pct), 0.0)
    return {
        "manual_only": True,
        "trade_execution": False,
        "broker_writes": False,
        "portfolio_equity": eq,
        "hedge_notional": eq * hp,
        "estimated_put_cost": round(cost, 2),
        "disclaimer": "Advisory scenario only. Not an order. Not a return guarantee.",
    }
