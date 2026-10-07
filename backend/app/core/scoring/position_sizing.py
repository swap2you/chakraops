# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.4: Position sizing suggestions (informational only). Does not change mode_decision or Stage-2."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.scoring.config import (
    ACCOUNT_EQUITY_DEFAULT,
    MAX_CONTRACTS_PER_SYMBOL,
    MAX_NOTIONAL_PCT_PER_TRADE,
    MIN_FREE_CASH_PCT,
)


def compute_position_sizing(
    mode_decision: str,
    spot: float,
    stage2_trace: Optional[Dict[str, Any]],
    account_equity: float,
    holdings_shares: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Suggest contracts_suggested, capital_required_estimate, limiting_factor.
    Informational only; does not alter selection or mode.
    """
    mode = (mode_decision or "NONE").strip().upper()
    config = config or {}
    equity = float(account_equity) if account_equity is not None and account_equity > 0 else ACCOUNT_EQUITY_DEFAULT
    spot_val = float(spot) if spot is not None else 0.0
    holdings = int(holdings_shares) if holdings_shares is not None else 0
    if holdings < 0:
        holdings = 0

    max_contracts = config.get("MAX_CONTRACTS_PER_SYMBOL", MAX_CONTRACTS_PER_SYMBOL)
    max_notional_pct = config.get("MAX_NOTIONAL_PCT_PER_TRADE", MAX_NOTIONAL_PCT_PER_TRADE)
    min_free_pct = config.get("MIN_FREE_CASH_PCT", MIN_FREE_CASH_PCT)

    # Case A: mode_decision == NONE
    if mode == "NONE":
        return {
            "account_equity_used": equity,
            "mode": "NONE",
            "contracts_suggested": 0,
            "contracts_max_by_policy": max_contracts,
            "contracts_max_by_capital": 0,
            "capital_required_estimate": 0.0,
            "capital_pct_of_account": 0.0,
            "buffer_reserved_pct": min_free_pct,
            "limiting_factor": "MODE_NONE",
            "inputs": {
                "spot": spot_val,
                "strike_used": None,
                "strike_source": None,
                "holdings_shares": holdings if mode == "CC" else None,
            },
        }

    st2 = stage2_trace or {}
    sel = st2.get("selected_trade") if isinstance(st2, dict) else None

    # Case B: CSP
    if mode == "CSP":
        strike_used = None
        strike_source = None
        if isinstance(sel, dict) and sel.get("strike") is not None:
            try:
                strike_used = float(sel["strike"])
                strike_source = "stage2"
            except (TypeError, ValueError):
                pass
        if strike_used is None and spot_val > 0:
            strike_used = spot_val
            strike_source = "spot_estimate"

        if strike_used is None or strike_used <= 0:
            return {
                "account_equity_used": equity,
                "mode": "CSP",
                "contracts_suggested": 0,
                "contracts_max_by_policy": max_contracts,
                "contracts_max_by_capital": 0,
                "capital_required_estimate": 0.0,
                "capital_pct_of_account": 0.0,
                "buffer_reserved_pct": min_free_pct,
                "limiting_factor": "NO_STAGE2",
                "inputs": {"spot": spot_val, "strike_used": None, "strike_source": None, "holdings_shares": None},
            }

        capital_per_contract = strike_used * 100.0
        per_trade_budget = equity * max_notional_pct
        effective_budget = min(per_trade_budget, equity * (1.0 - min_free_pct))
        contracts_max_by_capital = int(effective_budget / capital_per_contract) if capital_per_contract > 0 else 0
        contracts_max_by_policy = max_contracts
        contracts_suggested = min(max(0, min(contracts_max_by_capital, contracts_max_by_policy)), max_contracts)

        if contracts_suggested == 0:
            limiting_factor = "NO_STAGE2" if strike_source == "spot_estimate" and not sel else "CAPITAL_LIMIT"
        elif contracts_max_by_capital < contracts_max_by_policy:
            limiting_factor = "CAPITAL_LIMIT"
        else:
            limiting_factor = "POLICY_LIMIT" if contracts_suggested >= contracts_max_by_policy else "NONE"

        capital_required_estimate = contracts_suggested * capital_per_contract
        capital_pct = (capital_required_estimate / equity) if equity > 0 else 0.0

        return {
            "account_equity_used": equity,
            "mode": "CSP",
            "contracts_suggested": contracts_suggested,
            "contracts_max_by_policy": contracts_max_by_policy,
            "contracts_max_by_capital": contracts_max_by_capital,
            "capital_required_estimate": round(capital_required_estimate, 2),
            "capital_pct_of_account": round(capital_pct, 6),
            "buffer_reserved_pct": min_free_pct,
            "limiting_factor": limiting_factor,
            "inputs": {
                "spot": spot_val,
                "strike_used": strike_used,
                "strike_source": strike_source,
                "holdings_shares": None,
            },
        }

    # Case C: CC
    contracts_max_by_holdings = holdings // 100
    contracts_suggested = min(contracts_max_by_holdings, max_contracts)
    if holdings == 0:
        contracts_suggested = 0
        limiting_factor = "HOLDINGS_LIMIT"
    elif contracts_max_by_holdings < max_contracts:
        limiting_factor = "HOLDINGS_LIMIT"
    else:
        limiting_factor = "POLICY_LIMIT" if contracts_suggested >= max_contracts else "NONE"

    strike_used = None
    strike_source = None
    if isinstance(sel, dict) and sel.get("strike") is not None:
        try:
            strike_used = float(sel["strike"])
            strike_source = "stage2"
        except (TypeError, ValueError):
            pass

    return {
        "account_equity_used": equity,
        "mode": "CC",
        "contracts_suggested": contracts_suggested,
        "contracts_max_by_policy": max_contracts,
        "contracts_max_by_capital": None,
        "capital_required_estimate": 0.0,
        "capital_pct_of_account": 0.0,
        "buffer_reserved_pct": min_free_pct,
        "limiting_factor": limiting_factor,
        "inputs": {
            "spot": spot_val,
            "strike_used": strike_used,
            "strike_source": strike_source,
            "holdings_shares": holdings,
        },
    }
