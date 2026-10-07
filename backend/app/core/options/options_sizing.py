# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.0: Options position sizing (request-time only; never persisted)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.core.config.trade_rules import (
    OPTIONS_MAX_NOTIONAL_PCT,
    OPTIONS_MAX_CONTRACTS_PER_TRADE,
    OPTIONS_RISK_PCT_PER_TRADE_DEFAULT,
)
from app.core.eval.decision_artifact_v2 import normalize_contract_key


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _find_selected_candidate(
    c_dicts: List[Dict[str, Any]],
    selected_contract_key: Optional[str],
    strategy: str,
) -> Optional[Dict[str, Any]]:
    """Return the candidate dict that matches selected_contract_key, or first candidate if key is None."""
    if not c_dicts:
        return None
    strat_upper = (strategy or "CSP").strip().upper()
    opt_type = "PUT" if strat_upper == "CSP" else "CALL"
    key_to_match = (selected_contract_key or "").strip()
    for c in c_dicts:
        strike = c.get("strike")
        exp = c.get("expiration") or c.get("expiry")
        if strike is None and exp is None:
            continue
        exp_str = str(exp).strip()[:10] if exp else None
        built = normalize_contract_key(_float(strike), exp_str, opt_type)
        if built and built == key_to_match:
            return c
    if key_to_match and c_dicts:
        return c_dicts[0]
    return c_dicts[0] if c_dicts else None


def build_options_sizing_r240(
    c_dicts: List[Dict[str, Any]],
    selected_contract_key: Optional[str],
    strategy: Optional[str],
    account_summary: Optional[Dict[str, Any]],
    shares_position: Optional[Dict[str, Any]],
    spot: Optional[float],
) -> Dict[str, Any]:
    """
    R24.0: Compute options_sizing for symbol-diagnostics (request-time only).
    Returns basis (OK | INSUFFICIENT_DATA | NO_SELECTED_CANDIDATE), suggested_contracts,
    required_cash, credit_estimate, risk_pct_used, notes_codes (codes only; no FAIL_/WARN_).
    """
    out: Dict[str, Any] = {
        "basis": "NO_SELECTED_CANDIDATE",
        "suggested_contracts": None,
        "required_cash": None,
        "credit_estimate": None,
        "risk_pct_used": None,
        "notes_codes": [],
    }
    strat = (strategy or "CSP").strip().upper()
    if strat not in ("CSP", "CC"):
        strat = "CSP"

    selected = _find_selected_candidate(c_dicts, selected_contract_key, strat)
    if not selected:
        return out

    strike = _float(selected.get("strike"))
    mid = _float(selected.get("mid"))
    bid = _float(selected.get("bid"))
    ask = _float(selected.get("ask"))
    premium = mid if mid is not None else (bid if bid is not None else ask)
    if premium is None and ask is not None:
        premium = ask

    if not account_summary:
        out["basis"] = "INSUFFICIENT_DATA"
        return out

    account_value = _float(account_summary.get("total_capital"))
    cash = _float(account_summary.get("cash"))
    buying_power = _float(account_summary.get("buying_power"))
    available_cash = buying_power if (buying_power and buying_power > 0) else cash
    if account_value is None and available_cash is not None:
        account_value = available_cash
    if account_value is None or account_value <= 0:
        out["basis"] = "INSUFFICIENT_DATA"
        return out

    notes: List[str] = []
    suggested_contracts = 0
    required_cash: Optional[float] = None
    risk_pct_used: Optional[float] = None

    if strat == "CSP":
        if strike is None or strike <= 0:
            out["basis"] = "NO_SELECTED_CANDIDATE"
            return out
        notional_per = strike * 100
        max_by_cash = int(available_cash / notional_per) if (available_cash and available_cash > 0) else 0
        max_by_notional = int((account_value * OPTIONS_MAX_NOTIONAL_PCT) / notional_per) if notional_per > 0 else 0
        suggested_contracts = min(
            max_by_cash,
            OPTIONS_MAX_CONTRACTS_PER_TRADE,
            max_by_notional if max_by_notional > 0 else OPTIONS_MAX_CONTRACTS_PER_TRADE,
        )
        if suggested_contracts >= 1:
            required_cash = strike * 100 * suggested_contracts
            risk_pct_used = (required_cash / account_value) if account_value else None
            notes.append("SIZED_BY_CASH_SECURED")
            if suggested_contracts >= OPTIONS_MAX_CONTRACTS_PER_TRADE:
                notes.append("LIMITED_BY_MAX_CONTRACTS")
            if max_by_notional > 0 and suggested_contracts >= max_by_notional:
                notes.append("LIMITED_BY_NOTIONAL_PCT")
        out["basis"] = "OK"
        out["required_cash"] = round(required_cash, 2) if required_cash is not None else None
        out["risk_pct_used"] = round(risk_pct_used, 4) if risk_pct_used is not None else None
    else:
        # CC: limited by covered shares
        covered_shares = 0
        if shares_position and isinstance(shares_position.get("quantity"), (int, float)):
            covered_shares = int(shares_position["quantity"])
        max_contracts_by_shares = max(0, covered_shares // 100) if covered_shares else 0
        suggested_contracts = min(max_contracts_by_shares, OPTIONS_MAX_CONTRACTS_PER_TRADE)
        if suggested_contracts >= 1:
            required_cash = 0.0
            risk_pct_used = None
            notes.append("SIZED_BY_COVERED_SHARES")
            if suggested_contracts >= OPTIONS_MAX_CONTRACTS_PER_TRADE:
                notes.append("LIMITED_BY_MAX_CONTRACTS")
        out["basis"] = "OK"
        out["required_cash"] = 0.0 if suggested_contracts else None
        out["risk_pct_used"] = None

    out["suggested_contracts"] = suggested_contracts if suggested_contracts else None
    if premium is not None and suggested_contracts and suggested_contracts > 0:
        out["credit_estimate"] = round(premium * 100 * suggested_contracts, 2)
    else:
        out["credit_estimate"] = None
    out["notes_codes"] = notes
    return out
