# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.2: Lifecycle computation for tracked positions — premium_captured, DTE, alert flags."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.positions.models import Position


def compute_dte(expiration: Optional[str]) -> Optional[int]:
    """Days to expiration. None if no expiration or invalid."""
    if not expiration:
        return None
    try:
        if "T" in str(expiration):
            exp = datetime.fromisoformat(str(expiration).replace("Z", "+00:00")).date()
        else:
            exp = datetime.strptime(str(expiration).strip()[:10], "%Y-%m-%d").date()
        today = date.today()
        return (exp - today).days
    except (ValueError, TypeError):
        return None


def compute_premium_captured_pct(entry_credit: Optional[float], mark: Optional[float]) -> Optional[float]:
    """Premium captured as percentage of entry credit. (entry - mark) / entry * 100. None if missing data."""
    if entry_credit is None or entry_credit <= 0 or mark is None:
        return None
    return round((1.0 - (mark / entry_credit)) * 100.0, 2)


def compute_alert_flags(
    premium_captured_pct: Optional[float],
    dte: Optional[int],
    underlying_price: Optional[float],
    stop_price: Optional[float],
) -> List[str]:
    """Alert flags: T1 (>=60%), T2 (>=80%), T3 (>=95%), DTE_RISK (<=3), STOP (underlying <= stop)."""
    flags: List[str] = []
    if premium_captured_pct is not None:
        if premium_captured_pct >= 95:
            flags.append("T3")
        elif premium_captured_pct >= 80:
            flags.append("T2")
        elif premium_captured_pct >= 60:
            flags.append("T1")
    if dte is not None and dte <= 3:
        flags.append("DTE_RISK")
    if stop_price is not None and underlying_price is not None and underlying_price <= stop_price:
        flags.append("STOP")
    return flags


def enrich_position_for_portfolio(
    p: Position,
    mark_by_position_id: Optional[Dict[str, float]] = None,
    underlying_by_symbol: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Enrich a position with lifecycle fields for portfolio UI.
    Phase 15.0: Mark from position.mark_price_per_contract or mark_by_position_id.
    Unrealized PnL: open_credit - mark_debit_total - open_fees (premium convention).
    """
    d = p.to_dict()
    position_id = p.position_id
    symbol = (p.symbol or "").strip().upper()
    entry_credit = p.credit_expected or p.open_credit
    mark = getattr(p, "mark_price_per_contract", None) or (mark_by_position_id or {}).get(position_id)
    underlying = (underlying_by_symbol or {}).get(symbol) if symbol else None
    expiry = p.expiration
    dte = compute_dte(expiry)
    premium_pct = compute_premium_captured_pct(entry_credit, mark)
    alert_flags = compute_alert_flags(premium_pct, dte, underlying, p.stop_price)
    d["dte"] = dte
    d["mark"] = mark
    d["premium_captured_pct"] = premium_pct
    d["alert_flags"] = alert_flags
    d["unrealized_pnl"] = None
    if mark is not None and p.contracts:
        open_credit = p.open_credit or (entry_credit and float(entry_credit) * int(p.contracts))
        if open_credit is not None:
            mark_debit_total = mark * 100 * int(p.contracts)
            open_fees = getattr(p, "open_fees", None) or 0
            d["unrealized_pnl"] = round(open_credit - mark_debit_total - open_fees, 2)
    return d
