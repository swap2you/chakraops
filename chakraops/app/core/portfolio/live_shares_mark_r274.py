# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.4: Request-time mark/unrealized for live shares positions. R27.7: pct_return, days_held, cc_eligible. No FAIL_/WARN_."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.lifecycle.position_lifecycle_r243 import select_mark_from_quote

# R27.7: Standard lot for CC readiness (safe; no raw eligibility codes in this module)
CC_MIN_SHARES = 100


def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO date/datetime; return None if missing or invalid."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s + "T00:00:00+00:00")
    except (ValueError, TypeError):
        return None


def enrich_live_shares_positions_with_mark(
    positions: List[Dict[str, Any]],
    price_by_symbol: Dict[str, float],
    quote_ts_iso: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    R27.4: Add request-time mark_value, mark_source, quote_ts, mark_age_sec, unrealized_pl.
    R27.7: pct_return, days_held, cc_eligible, cc_eligible_reason (safe labels only).
    Returns new list sorted by symbol for determinism. Missing quote -> nulls (UI shows "—").
    """
    as_of_ts = time.time()
    now_utc = datetime.now(timezone.utc)
    result: List[Dict[str, Any]] = []
    for pos in positions:
        out = dict(pos)
        sym = (pos.get("symbol") or "").strip().upper()
        qty = int(pos.get("quantity") or 0)
        avg_cost = pos.get("avg_cost")
        opened_at_raw = pos.get("opened_at")
        if sym not in price_by_symbol or qty <= 0:
            out["mark_value"] = None
            out["mark_source"] = None
            out["quote_ts"] = None
            out["mark_age_sec"] = None
            out["unrealized_pl"] = None
            out["pct_return"] = None
            out["days_held"] = None
            out["cc_eligible"] = qty >= CC_MIN_SHARES
            out["cc_eligible_reason"] = "Standard lot (100+ shares)" if qty >= CC_MIN_SHARES else "Fewer than 100 shares"
            result.append(out)
            continue
        last_price = price_by_symbol[sym]
        mark_value, mark_source, quote_ts, mark_age_sec = select_mark_from_quote(
            last=last_price,
            quote_ts=quote_ts_iso,
            as_of_ts=as_of_ts,
        )
        out["mark_value"] = round(mark_value, 4) if mark_value is not None else None
        out["mark_source"] = mark_source
        out["quote_ts"] = quote_ts
        out["mark_age_sec"] = mark_age_sec
        if mark_value is not None and avg_cost is not None:
            out["unrealized_pl"] = round((float(mark_value) - float(avg_cost)) * qty, 2)
        else:
            out["unrealized_pl"] = None
        if mark_value is not None and avg_cost is not None and float(avg_cost) != 0:
            out["pct_return"] = round((float(mark_value) - float(avg_cost)) / float(avg_cost) * 100, 2)
        else:
            out["pct_return"] = None
        opened_dt = _parse_iso_date(opened_at_raw)
        if opened_dt is not None:
            delta = now_utc - opened_dt
            out["days_held"] = max(0, delta.days)
        else:
            out["days_held"] = None
        out["cc_eligible"] = qty >= CC_MIN_SHARES
        out["cc_eligible_reason"] = "Standard lot (100+ shares)" if qty >= CC_MIN_SHARES else "Fewer than 100 shares"
        result.append(out)
    result.sort(key=lambda p: (p.get("symbol") or "").upper())
    return result
