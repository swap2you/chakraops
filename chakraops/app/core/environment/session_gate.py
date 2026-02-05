# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Session-aware execution gate (Phase 4.5.3).

Blocks new trades on short (early-close) sessions and when there are
insufficient trading days until option expiry.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from app.core.environment.market_calendar import (
    is_short_session,
    trading_days_until,
)


def check_session_gate(
    today: date,
    expiry_date: date | None,
    config: Dict[str, Any],
) -> List[str]:
    """Return list of execution gate reason codes if session/expiry rules fail; else [].

    Rules:
    - If block_short_sessions is True and today is a short session → "SHORT_SESSION".
    - If expiry_date is set and trading_days_until(expiry_date) < min_trading_days_to_expiry
      → "INSUFFICIENT_TRADING_DAYS".

    Parameters
    ----------
    today : date
        Reference date (e.g. date.today() or snapshot as_of date).
    expiry_date : date or None
        Option expiry date of the proposed trade. If None, the trading-days rule is skipped.
    config : dict
        Must contain min_trading_days_to_expiry (int) and block_short_sessions (bool).

    Returns
    -------
    List[str]
        Empty if pass; otherwise ["SHORT_SESSION"], ["INSUFFICIENT_TRADING_DAYS"], or both.
    """
    reasons: List[str] = []

    block_short = config.get("block_short_sessions", True)
    if block_short and is_short_session(today):
        reasons.append("SHORT_SESSION")

    min_days = config.get("min_trading_days_to_expiry", 5)
    try:
        min_days = int(min_days)
    except (TypeError, ValueError):
        min_days = 5

    if expiry_date is not None and min_days > 0:
        tdays = trading_days_until(expiry_date, from_date=today)
        if tdays < min_days:
            reasons.append("INSUFFICIENT_TRADING_DAYS")

    return reasons
