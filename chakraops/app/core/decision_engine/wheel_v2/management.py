# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 open-option management — CLOSE / ROLL / HOLD via position_lifecycle_r243."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Union

from app.core.lifecycle.position_lifecycle_r243 import (
    PROFIT_TARGET_PCT_DEFAULT,
    ROLL_WINDOW_DTE_DEFAULT,
    compute_position_lifecycle,
)
from app.core.decision_engine.profiles import StrategyProfile

# Defaults align with strategy_profiles.yaml profit_management keys.
_DEFAULT_TAKE_PROFIT_PCT = PROFIT_TARGET_PCT_DEFAULT
_DEFAULT_ROLL_AT_DTE = ROLL_WINDOW_DTE_DEFAULT


def _profit_thresholds(profile: Optional[Union[StrategyProfile, Mapping[str, Any]]]) -> tuple:
    """Extract (take_profit_pct, roll_at_dte) from profile.profit_management when available."""
    pm: Mapping[str, Any] = {}
    if profile is None:
        return (_DEFAULT_TAKE_PROFIT_PCT, _DEFAULT_ROLL_AT_DTE)
    if isinstance(profile, StrategyProfile):
        pm = profile.profit_management or {}
    elif isinstance(profile, Mapping):
        raw = profile.get("profit_management") or profile
        pm = raw if isinstance(raw, Mapping) else {}
    else:
        pm = getattr(profile, "profit_management", None) or {}
        if not isinstance(pm, Mapping):
            pm = {}
    take = pm.get("take_profit_pct", _DEFAULT_TAKE_PROFIT_PCT)
    roll = pm.get("roll_at_dte", _DEFAULT_ROLL_AT_DTE)
    try:
        take_f = float(take)
    except (TypeError, ValueError):
        take_f = _DEFAULT_TAKE_PROFIT_PCT
    try:
        roll_i = int(roll)
    except (TypeError, ValueError):
        roll_i = _DEFAULT_ROLL_AT_DTE
    return (take_f, roll_i)


def manage_open_option(
    position: Any,
    profile: Optional[Union[StrategyProfile, Mapping[str, Any]]] = None,
    *,
    spot: Optional[float] = None,
    mark_proxy: Optional[float] = None,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    last: Optional[float] = None,
    quote_ts: Optional[str] = None,
    as_of_ts: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Recommend CLOSE / ROLL / HOLD for an open CSP or CC.

    Uses ``compute_position_lifecycle`` with profile ``profit_management``
    thresholds (``take_profit_pct``, ``roll_at_dte``) when available.
    Request-time only — never persist to decision_latest.json.
    """
    take_profit_pct, roll_at_dte = _profit_thresholds(profile)
    life = compute_position_lifecycle(
        position,
        spot=spot,
        mark_proxy=mark_proxy,
        bid=bid,
        ask=ask,
        last=last,
        quote_ts=quote_ts,
        as_of_ts=as_of_ts,
        profit_target_pct=take_profit_pct,
        roll_window_dte=roll_at_dte,
        recommended_by="r38_wheel_v2",
    )
    action = (life.get("recommended_action_code") or "HOLD").upper()
    if action not in ("CLOSE", "ROLL", "HOLD"):
        action = "HOLD"
    return {
        "action": action,
        "pct_max_profit": life.get("pct_max_profit"),
        "dte": life.get("dte"),
        "assignment_risk": life.get("assignment_risk"),
        "roll_window": life.get("roll_window"),
        "profit_target_pct": take_profit_pct,
        "roll_at_dte": roll_at_dte,
        "lifecycle": life,
        "manual_only": True,
        "trade_execution": False,
    }
