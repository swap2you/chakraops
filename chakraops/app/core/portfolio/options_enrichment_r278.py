# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.8: Request-time enrichment for tracked option positions (portfolio + ticket parity).
   mark_value/source/age, unrealized proxy, dte, pct_max_profit, lifecycle_recommend + lifecycle_reason.
   All payload strings safe (no FAIL_/WARN_). Deterministic sort."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.core.positions.models import Position


def _safe_lifecycle_recommend(code: Optional[str]) -> str:
    """Map recommended_action_code to safe UI label. No FAIL_/WARN_."""
    if not code:
        return "Hold"
    c = (code or "").strip().upper()
    if c == "CLOSE":
        return "Close"
    if c == "ROLL":
        return "Roll"
    return "Hold"


def _safe_lifecycle_reason(lc: Dict[str, Any]) -> str:
    """Single safe reason label from lifecycle output. No FAIL_/WARN_."""
    rec = (lc.get("recommended_action_code") or "").strip().upper()
    if rec == "CLOSE":
        if lc.get("assignment_risk", {}).get("active"):
            return "Assignment risk"
        if lc.get("pct_max_profit") is not None and lc.get("pct_max_profit", 0) >= 50:
            return "Profit target reached"
        return "Close"
    if rec == "ROLL":
        return "Roll window"
    return "Hold"


def enrich_options_positions_for_portfolio(
    positions: List[Position],
    underlying_by_symbol: Optional[Dict[str, float]] = None,
    quote_ts_iso: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    R27.8: Enrich open CSP/CC positions with mark_value, mark_source, mark_age_sec,
    unrealized proxy (from mark vs entry), dte, pct_max_profit, lifecycle_recommend, lifecycle_reason.
    Uses consistent as_of_ts; mark from position or MID→LAST→BID→ASK when quote provided.
    Returns list sorted by (symbol, expiration, strike) for determinism. All strings safe.
    """
    from app.core.positions.lifecycle import enrich_position_for_portfolio
    from app.core.lifecycle.position_lifecycle_r243 import compute_position_lifecycle

    as_of_ts = time.time()
    underlying_by_symbol = underlying_by_symbol or {}
    open_statuses = ("OPEN", "PARTIAL_EXIT")
    result: List[Dict[str, Any]] = []
    for p in positions:
        s = (p.status or "").upper()
        if s not in open_statuses:
            continue
        strat = (p.strategy or "").upper()
        if strat not in ("CSP", "CC"):
            continue
        # Base enrichment (dte, mark, premium_captured_pct, alert_flags, unrealized_pnl)
        base = enrich_position_for_portfolio(p, {}, underlying_by_symbol)
        # Lifecycle (mark_value/source/age, pct_max_profit, recommended_action_code, etc.)
        mark_proxy = getattr(p, "mark_price_per_contract", None)
        quote_ts = quote_ts_iso or getattr(p, "mark_time_utc", None)
        spot = underlying_by_symbol.get((p.symbol or "").strip().upper()) if p.symbol else None
        lc = compute_position_lifecycle(
            p,
            spot=spot,
            mark_proxy=mark_proxy,
            quote_ts=quote_ts,
            as_of_ts=as_of_ts,
        )
        # Merge: ensure mark_value, mark_source, mark_age_sec (use lifecycle when present)
        base["mark_value"] = lc.get("mark_value")
        base["mark_source"] = lc.get("mark_source") or ("UNKNOWN" if base.get("mark") is not None else None)
        base["mark_age_sec"] = lc.get("mark_age_sec")
        base["quote_ts"] = lc.get("quote_ts") or quote_ts
        base["pct_max_profit"] = lc.get("pct_max_profit")
        base["lifecycle_recommend"] = _safe_lifecycle_recommend(lc.get("recommended_action_code"))
        base["lifecycle_reason"] = _safe_lifecycle_reason(lc)
        # R27.8: No raw FAIL/WARN in payload — map data_sufficiency for display
        ds = base.get("data_sufficiency")
        if ds in ("FAIL", "WARN"):
            base["data_sufficiency"] = "Review"
        # Unrealized proxy already in base from enrich_position_for_portfolio
        result.append(base)
    result.sort(key=lambda x: (
        (x.get("symbol") or "").upper(),
        x.get("expiration") or "",
        float(x.get("strike") or 0),
    ))
    return result
