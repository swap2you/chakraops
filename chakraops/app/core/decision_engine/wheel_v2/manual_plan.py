# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 manual plan builder — complete advisory ticket fields (request-time only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Union

from app.core.decision_engine.profiles import StrategyProfile
from app.core.decision_engine.wheel_v2.contract import ManualPlan


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _pm(profile: Optional[Union[StrategyProfile, Mapping[str, Any]]]) -> Dict[str, Any]:
    if profile is None:
        return {}
    if isinstance(profile, StrategyProfile):
        return dict(profile.profit_management or {})
    if isinstance(profile, Mapping):
        raw = profile.get("profit_management") or {}
        return dict(raw) if isinstance(raw, Mapping) else {}
    raw = getattr(profile, "profit_management", None) or {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def build_manual_plan(
    *,
    strategy: Optional[str] = None,
    action: Optional[str] = None,
    strike: Optional[float] = None,
    expiry: Optional[str] = None,
    dte: Optional[int] = None,
    delta: Optional[float] = None,
    premium: Optional[float] = None,
    contracts: Optional[int] = None,
    shares: Optional[int] = None,
    earnings_days: Optional[int] = None,
    profile: Optional[Union[StrategyProfile, Mapping[str, Any]]] = None,
    assignment_plan: Optional[str] = None,
    thesis_failure_plan: Optional[str] = None,
    staged_tranches: Optional[List[Dict[str, Any]]] = None,
    sources: Optional[List[str]] = None,
    as_of_utc: Optional[str] = None,
    contract: Optional[Mapping[str, Any]] = None,
    summary_label: Optional[str] = None,
) -> ManualPlan:
    """
    Build a complete manual plan: strike, expiry, dte, delta, premium, breakeven
    (strike - premium for CSP), collateral, earnings_days, profit_target, roll_dte,
    assignment_plan, thesis_failure_plan, timestamps, sources.
    """
    c = contract or {}
    strike_v = _f(strike if strike is not None else c.get("strike"))
    expiry_v = expiry if expiry is not None else c.get("expiry") or c.get("expiration")
    dte_v = _i(dte if dte is not None else c.get("dte"))
    delta_v = _f(delta if delta is not None else c.get("delta"))
    premium_v = _f(premium if premium is not None else c.get("premium") or c.get("credit"))
    strat = (strategy or c.get("strategy") or "").upper() or None

    breakeven = None
    if strike_v is not None and premium_v is not None:
        if strat == "CSP":
            breakeven = round(strike_v - premium_v, 4)
        elif strat in ("CC", "COVERED_CALL"):
            breakeven = round(strike_v + premium_v, 4)

    contracts_i = _i(contracts if contracts is not None else c.get("contracts")) or 0
    collateral = None
    if strat == "CSP" and strike_v is not None and contracts_i > 0:
        collateral = round(strike_v * 100 * contracts_i, 2)

    pm = _pm(profile)
    profit_target = _f(pm.get("take_profit_pct"))
    roll_dte = _i(pm.get("roll_at_dte"))
    if profit_target is None:
        profit_target = 50.0
    if roll_dte is None:
        roll_dte = 21

    qty = contracts_i if strat in ("CSP", "CC", "COVERED_CALL") else (_i(shares) or 0)

    ts = as_of_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    src = list(sources or ["wheel_v2", "profit_management"])

    label = summary_label
    if not label:
        parts = []
        if action:
            parts.append(str(action))
        if strat:
            parts.append(strat)
        if strike_v is not None:
            parts.append(f"strike {strike_v:g}")
        if expiry_v:
            parts.append(str(expiry_v)[:10])
        label = " · ".join(parts) if parts else "Manual advisory plan"

    return ManualPlan(
        strike=strike_v,
        expiry=str(expiry_v) if expiry_v else None,
        dte=dte_v,
        delta=delta_v,
        premium=premium_v,
        breakeven=breakeven,
        collateral=collateral,
        earnings_days=_i(earnings_days),
        profit_target_pct=profit_target,
        roll_dte=roll_dte,
        assignment_plan=assignment_plan,
        thesis_failure_plan=thesis_failure_plan,
        strategy=strat,
        action=action,
        quantity=qty if qty else None,
        staged_tranches=list(staged_tranches) if staged_tranches else None,
        as_of_utc=ts,
        sources=src,
        summary_label=label,
    )
