# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.4: Request-time mark/unrealized for live shares positions. Centralized mark selection (MID→LAST→BID→ASK). No FAIL_/WARN_."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.core.lifecycle.position_lifecycle_r243 import select_mark_from_quote


def enrich_live_shares_positions_with_mark(
    positions: List[Dict[str, Any]],
    price_by_symbol: Dict[str, float],
    quote_ts_iso: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    R27.4: Add request-time mark_value, mark_source, quote_ts, mark_age_sec, unrealized_pl
    to live shares positions. Uses centralized select_mark_from_quote (LAST when single price).
    Returns new list; does not mutate input. Missing quote -> nulls (UI shows "—").
    """
    as_of_ts = time.time()
    result: List[Dict[str, Any]] = []
    for pos in positions:
        out = dict(pos)
        sym = (pos.get("symbol") or "").strip().upper()
        qty = int(pos.get("quantity") or 0)
        avg_cost = pos.get("avg_cost")
        if sym not in price_by_symbol or qty <= 0:
            out["mark_value"] = None
            out["mark_source"] = None
            out["quote_ts"] = None
            out["mark_age_sec"] = None
            out["unrealized_pl"] = None
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
        result.append(out)
    return result
