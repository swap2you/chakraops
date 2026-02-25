# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.3: Request-time lifecycle for tracked option positions. No persistence to decision artifacts.
R24.4: Mark proxy provenance/freshness (mark_value, mark_source, quote_ts, mark_age_sec) + roll rationale."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Tuple

# Conservative defaults (no gambling)
PROFIT_TARGET_PCT_DEFAULT = 50.0
ROLL_WINDOW_DTE_DEFAULT = 14
ASSIGNMENT_RISK_DTE_MAX = 3
RECOMMENDED_BY = "r243"

# R24.4: Mark source enum (safe for UI; never persisted to decision artifacts)
MARK_SOURCE_MID = "MID"
MARK_SOURCE_LAST = "LAST"
MARK_SOURCE_BIDASK_MID = "BIDASK_MID"
MARK_SOURCE_BID = "BID"
MARK_SOURCE_ASK = "ASK"
MARK_SOURCE_UNKNOWN = "UNKNOWN"


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


def _valid_mark(x: Optional[float]) -> bool:
    """True if x is a finite positive number (valid for option mark)."""
    if x is None:
        return False
    try:
        f = float(x)
        return f >= 0 and f == f  # finite, non-NaN
    except (TypeError, ValueError):
        return False


def select_mark_from_quote(
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    last: Optional[float] = None,
    quote_ts: Optional[str] = None,
    as_of_ts: Optional[float] = None,
) -> Tuple[Optional[float], str, Optional[str], Optional[int]]:
    """
    R24.4: Deterministic mark selection from quote. Returns (mark_value, mark_source, quote_ts, mark_age_sec).
    Order: MID (bid+ask valid) -> LAST -> BIDASK_MID -> BID -> ASK -> UNKNOWN.
    """
    mark: Optional[float] = None
    source = MARK_SOURCE_UNKNOWN
    out_ts: Optional[str] = quote_ts
    age_sec: Optional[int] = None

    # Deterministic order: MID (bid+ask) -> LAST -> BID -> ASK -> UNKNOWN
    if _valid_mark(bid) and _valid_mark(ask):
        mark = round((float(bid) + float(ask)) / 2.0, 4)
        source = MARK_SOURCE_MID
    elif _valid_mark(last):
        mark = round(float(last), 4)
        source = MARK_SOURCE_LAST
    elif _valid_mark(bid):
        mark = round(float(bid), 4)
        source = MARK_SOURCE_BID
    elif _valid_mark(ask):
        mark = round(float(ask), 4)
        source = MARK_SOURCE_ASK

    if quote_ts and as_of_ts is not None:
        try:
            qt = datetime.fromisoformat(quote_ts.replace("Z", "+00:00"))
            if qt.tzinfo is None:
                qt = qt.replace(tzinfo=timezone.utc)
            age_sec = int(as_of_ts - qt.timestamp())
            if age_sec < 0:
                age_sec = 0
        except (ValueError, TypeError, OSError):
            pass

    return (mark, source, out_ts, age_sec)


def compute_position_lifecycle(
    position: Any,
    spot: Optional[float] = None,
    mark_proxy: Optional[float] = None,
    *,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    last: Optional[float] = None,
    quote_ts: Optional[str] = None,
    as_of_ts: Optional[float] = None,
    profit_target_pct: float = PROFIT_TARGET_PCT_DEFAULT,
    roll_window_dte: int = ROLL_WINDOW_DTE_DEFAULT,
    assignment_risk_dte_max: int = ASSIGNMENT_RISK_DTE_MAX,
) -> Dict[str, Any]:
    """
    Request-time lifecycle for a single tracked option position (CSP/CC).
    Returns structured fields only; never persist to decision_latest.json.
    Same inputs -> same outputs (deterministic).
    R24.4: Optional bid/ask/last/quote_ts/as_of_ts for mark provenance and freshness.
    """
    out: Dict[str, Any] = {
        "pct_max_profit": None,
        "dte": None,
        "mark_proxy": None,
        "mark_value": None,
        "mark_source": None,
        "quote_ts": None,
        "mark_age_sec": None,
        "assignment_risk": {"active": False, "reason_code": None},
        "roll_window": {"active": False, "dte": None},
        "recommended_action_code": "HOLD",
        "recommended_by": RECOMMENDED_BY,
        "roll_window_threshold_dte": None,
        "roll_reason_codes": None,
    }
    strategy = (getattr(position, "strategy", None) or "").upper()
    if strategy not in ("CSP", "CC"):
        return out

    expiry = getattr(position, "expiration", None) or getattr(position, "expiry", None)
    strike = _float(getattr(position, "strike", None))
    entry_credit = _float(getattr(position, "open_credit", None)) or _float(getattr(position, "credit_expected", None))

    # R24.4: Mark from quote when available (deterministic selection)
    mark = None
    if bid is not None or ask is not None or last is not None:
        mark_val, mark_src, qts, age_sec = select_mark_from_quote(bid=bid, ask=ask, last=last, quote_ts=quote_ts, as_of_ts=as_of_ts)
        if mark_val is not None:
            mark = mark_val
            out["mark_value"] = mark_val
            out["mark_source"] = mark_src
            out["quote_ts"] = qts
            out["mark_age_sec"] = age_sec
    if mark is None:
        mark = mark_proxy if mark_proxy is not None else _float(getattr(position, "mark_price_per_contract", None))
        if mark is not None:
            out["mark_value"] = round(float(mark), 4)
            out["mark_source"] = MARK_SOURCE_UNKNOWN

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
        # R24.4: Roll rationale (safe enums only; not persisted to decision artifact)
        out["roll_window_threshold_dte"] = roll_window_dte
        out["roll_reason_codes"] = ["DTE_WINDOW"]
    else:
        out["recommended_action_code"] = "HOLD"

    return out
