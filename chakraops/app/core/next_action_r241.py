# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.1: Position-aware next_action_code and next_action_details (request-time only, never persisted)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

NextActionCode = str  # ENTRY | HOLD | CLOSE | ROLL | REDUCE | NONE


def _float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_num(v: Any) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        if f == int(f):
            return str(int(f))
        return "%.2f" % f
    except (TypeError, ValueError):
        return str(v) if v is not None else "—"


def compute_next_action_options(
    *,
    has_open_option: bool,
    selected_contract_key: Optional[str],
    exit_plan: Dict[str, Any],
    spot: Optional[float],
    delta_best: Optional[float] = None,
    dte: Optional[int] = None,
    strategy: Optional[str] = None,
) -> tuple[NextActionCode, List[str], Dict[str, Any]]:
    """
    Compute next_action for OPTIONS (CSP/CC). Returns (code, rationale_lines, key_numbers).
    ROLL when near DTE threshold or risk flags (safe codes only); no raw FAIL_/WARN_.
    """
    rationale: List[str] = []
    stop_price = _float_or_none(exit_plan.get("stop"))
    t1 = _float_or_none(exit_plan.get("t1"))
    targets_exceeded = exit_plan.get("targets_already_exceeded") or False
    spot_val = _float_or_none(spot)
    key_numbers: Dict[str, Any] = {
        "spot": spot,
        "t1": t1,
        "delta_best": delta_best,
        "dte": dte,
    }

    # CLOSE: position open and (stop hit or target hit)
    if has_open_option:
        stop_hit = stop_price is not None and spot_val is not None and spot_val <= stop_price
        target_hit = targets_exceeded or (t1 is not None and spot_val is not None and spot_val >= t1)
        if stop_hit:
            rationale.append("Stop level reached; consider closing.")
            return "CLOSE", rationale, key_numbers
        if target_hit:
            rationale.append("Target reached; consider taking profit.")
            return "CLOSE", rationale, key_numbers
        # ROLL: near DTE threshold (e.g. &lt; 10 DTE) — use safe wording
        if dte is not None and dte <= 14:
            rationale.append("Low DTE; consider rolling or closing.")
            return "ROLL", rationale, key_numbers
        rationale.append("Position open; monitor levels.")
        return "HOLD", rationale, key_numbers

    # No position: ENTRY if we have a selected contract
    if selected_contract_key:
        rationale.append("Eligible for entry; no open position.")
        return "ENTRY", rationale, key_numbers

    return "NONE", [], key_numbers


def compute_next_action_shares(
    *,
    shares_eligible: bool,
    has_shares_position: bool,
    shares_plan: Optional[Dict[str, Any]] = None,
    exit_plan_or_targets: Optional[Dict[str, Any]] = None,
    spot: Optional[float] = None,
) -> tuple[NextActionCode, List[str], Dict[str, Any]]:
    """
    Compute next_action for SHARES. ENTRY when eligible and no position;
    CLOSE when target/stop hit if position exists; HOLD otherwise.
    """
    rationale: List[str] = []
    plan = shares_plan or {}
    ep = exit_plan_or_targets or {}
    t1 = _float_or_none(ep.get("t1"))
    if t1 is None and isinstance(plan.get("targets"), dict):
        t1 = _float_or_none(plan["targets"].get("t1"))
    stop_price = _float_or_none(ep.get("stop"))
    if stop_price is None and plan.get("stop") is not None:
        try:
            stop_price = float(plan["stop"])
        except (TypeError, ValueError):
            pass
    targets_exceeded = ep.get("targets_already_exceeded") or False
    spot_val = _float_or_none(spot)
    key_numbers: Dict[str, Any] = {"spot": spot, "t1": t1}

    if has_shares_position:
        stop_hit = stop_price is not None and spot_val is not None and spot_val <= stop_price
        target_hit = targets_exceeded or (t1 is not None and spot_val is not None and spot_val >= t1)
        if stop_hit:
            rationale.append("Stop level reached; consider closing shares.")
            return "CLOSE", rationale, key_numbers
        if target_hit:
            rationale.append("Target reached; consider taking profit.")
            return "CLOSE", rationale, key_numbers
        rationale.append("Shares position open; monitor levels.")
        return "HOLD", rationale, key_numbers

    if shares_eligible:
        rationale.append("Eligible for shares entry; no position.")
        return "ENTRY", rationale, key_numbers

    return "NONE", [], key_numbers


def build_next_action_details(
    strategy: Literal["OPTIONS", "SHARES"],
    next_action_code: NextActionCode,
    rationale_lines: List[str],
    key_numbers: Dict[str, Any],
    *,
    option_symbol: Optional[str] = None,
    contract_key: Optional[str] = None,
    premium_est: Optional[float] = None,
    profit_pct: Optional[float] = None,
) -> Dict[str, Any]:
    """Build next_action_details dict for symbol-diagnostics (request-time only)."""
    details: Dict[str, Any] = {
        "action": next_action_code,
        "rationale_lines": rationale_lines[:5],
        "key_numbers": {k: v for k, v in key_numbers.items() if v is not None},
    }
    if strategy == "OPTIONS":
        if contract_key:
            details["contract_key"] = contract_key
        if option_symbol:
            details["option_symbol"] = option_symbol
        if premium_est is not None:
            details["key_numbers"] = dict(details.get("key_numbers") or {})
            details["key_numbers"]["premium_est"] = premium_est
    if profit_pct is not None:
        details["key_numbers"] = dict(details.get("key_numbers") or {})
        details["key_numbers"]["profit_pct"] = profit_pct
    return details


def _recent_transitions() -> List[Dict[str, Any]]:
    """R24.1: Last 5 action transitions for Dashboard 'Recently changed'. In-memory stub; can wire to notifications store."""
    return []
