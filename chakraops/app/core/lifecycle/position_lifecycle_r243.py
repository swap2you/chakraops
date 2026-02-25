# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.3: Request-time lifecycle for tracked option positions. No persistence to decision artifacts."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

# Conservative defaults (no gambling)
PROFIT_TARGET_PCT_DEFAULT = 50.0
ROLL_WINDOW_DTE_DEFAULT = 14
ASSIGNMENT_RISK_DTE_MAX = 3
RECOMMENDED_BY = "r243"


def _float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _dte_from_expiry(expiry: Optional[str]) -> Optional[int]:
    if not expiry:
        return None
    try:
        if isinstance(expiry, str) and len(expiry) >= 10:
            exp = date.fromisoformat(expiry[:10])
            today = date.today()
            return (exp - today).days
    except (ValueError, TypeError):
        pass
    return None


def compute_position_lifecycle(
    position: Any,
    spot: Optional[float] = None,
    mark_proxy: Optional[float] = None,
    *,
    profit_target_pct: float = PROFIT_TARGET_PCT_DEFAULT,
    roll_window_dte: int = ROLL_WINDOW_DTE_DEFAULT,
    assignment_risk_dte_max: int = ASSIGNMENT_RISK_DTE_MAX,
) -> Dict[str, Any]:
    """
    Request-time lifecycle for a single tracked option position (CSP/CC).
    Returns structured fields only; never persist to decision_latest.json.
    Same inputs -> same outputs (deterministic).
    """
    out: Dict[str, Any] = {
        "pct_max_profit": None,
        "dte": None,
        "mark_proxy": None,
        "assignment_risk": {"active": False, "reason_code": None},
        "roll_window": {"active": False, "dte": None},
        "recommended_action_code": "HOLD",
        "recommended_by": RECOMMENDED_BY,
    }
    strategy = (getattr(position, "strategy", None) or "").upper()
    if strategy not in ("CSP", "CC"):
        return out

    expiry = getattr(position, "expiration", None) or getattr(position, "expiry", None)
    strike = _float(getattr(position, "strike", None))
    entry_credit = _float(getattr(position, "open_credit", None)) or _float(getattr(position, "credit_expected", None))
    mark = mark_proxy if mark_proxy is not None else _float(getattr(position, "mark_price_per_contract", None))

    dte = _dte_from_expiry(expiry)
    out["dte"] = dte
    out["mark_proxy"] = mark

    # pct_max_profit: for short options, profit % when buying back (credit - mark) / credit * 100
    if entry_credit is not None and entry_credit > 0 and mark is not None:
        # Max profit when mark -> 0; realized = entry_credit - mark (we received credit, pay mark to close)
        profit_pct = (entry_credit - mark) / entry_credit * 100.0
        out["pct_max_profit"] = round(profit_pct, 2)
    else:
        out["pct_max_profit"] = None

    # assignment_risk: ITM and low DTE (conservative)
    spot_val = _float(spot)
    itm = False
    if strike is not None and spot_val is not None:
        if strategy == "CSP":
            itm = spot_val < strike
        else:
            itm = spot_val > strike
    out["assignment_risk"] = {
        "active": bool(itm and dte is not None and dte <= assignment_risk_dte_max),
        "reason_code": "ITM_LOW_DTE" if (itm and dte is not None and dte <= assignment_risk_dte_max) else None,
    }

    # roll_window: DTE <= N
    out["roll_window"] = {
        "active": dte is not None and dte <= roll_window_dte,
        "dte": dte,
    }

    # recommended_action_code: deterministic priority
    if out["pct_max_profit"] is not None and out["pct_max_profit"] >= profit_target_pct:
        out["recommended_action_code"] = "CLOSE"
    elif out["assignment_risk"]["active"]:
        out["recommended_action_code"] = "CLOSE"
    elif out["roll_window"]["active"]:
        out["recommended_action_code"] = "ROLL"
    else:
        out["recommended_action_code"] = "HOLD"

    return out
