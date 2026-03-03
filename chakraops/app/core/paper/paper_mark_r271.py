# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.1: Request-time mark and unrealized P/L for paper positions. Not persisted. No FAIL_/WARN_."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.core.paper.paper_store_r270 import INSTRUMENT_OPTION, INSTRUMENT_SHARES, STATUS_OPEN
from app.core.lifecycle.position_lifecycle_r243 import select_mark_from_quote
from app.core.positions.quote_resolver import find_contract_quote


def _price_by_symbol_from_artifact(artifact: Any) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for s in getattr(artifact, "symbols", []) or []:
        sym = (getattr(s, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        p = getattr(s, "price", None) or getattr(s, "underlying_price", None)
        if p is not None:
            try:
                out[sym] = float(p)
            except (TypeError, ValueError):
                pass
    return out


def _candidates_by_symbol_from_artifact(artifact: Any) -> Dict[str, List[Dict[str, Any]]]:
    raw = getattr(artifact, "candidates_by_symbol", None) or {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for sym, rows in raw.items():
        sym_upper = (sym or "").strip().upper()
        if not sym_upper:
            continue
        if isinstance(rows, list):
            out[sym_upper] = [r if isinstance(r, dict) else (getattr(r, "__dict__", None) or {}) for r in rows]
        else:
            out[sym_upper] = []
    return out


def enrich_paper_positions_with_mark(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    R27.1: Add request-time mark_value, mark_source, mark_age_sec, quote_ts, unrealized_pl_usd
    to OPEN positions when quotes available. Closed positions unchanged. Deterministic mark order
    (MID->LAST->BID->ASK). Does not mutate input; returns new list with copied dicts.
    """
    result: List[Dict[str, Any]] = []
    as_of_ts = time.time()
    price_by_symbol: Dict[str, float] = {}
    candidates_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

    try:
        from app.core.eval.evaluation_store_v2 import get_evaluation_store_v2
        store = get_evaluation_store_v2()
        store.reload_from_disk()
        artifact = store.get_latest()
        if artifact:
            price_by_symbol = _price_by_symbol_from_artifact(artifact)
            candidates_by_symbol = _candidates_by_symbol_from_artifact(artifact)
    except Exception:
        pass

    for p in positions:
        pos = dict(p)
        status = (pos.get("status") or "").upper()
        if status != STATUS_OPEN:
            result.append(pos)
            continue

        instrument = (pos.get("instrument_type") or INSTRUMENT_SHARES).upper()
        symbol = (pos.get("symbol") or "").strip().upper()
        qty = int(pos.get("qty") or 0)
        open_price = float(pos.get("open_price") or 0)

        pos["mark_value"] = None
        pos["mark_source"] = None
        pos["mark_age_sec"] = None
        pos["quote_ts"] = None
        pos["unrealized_pl_usd"] = None

        if instrument == INSTRUMENT_SHARES:
            last_price = price_by_symbol.get(symbol)
            if last_price is not None:
                pos["mark_value"] = round(float(last_price), 4)
                pos["mark_source"] = "LAST"
                pos["unrealized_pl_usd"] = round((last_price - open_price) * qty, 2)
            result.append(pos)
            continue

        # OPTIONS: use contract quote, mark order MID->LAST->BID->ASK
        expiry = (pos.get("expiry") or "").strip()[:10] or None
        strike = pos.get("strike")
        right = (pos.get("right") or "P").strip().upper()
        opt_type = "PUT" if right in ("P", "PUT") else "CALL"
        chain_rows = candidates_by_symbol.get(symbol, [])
        quote = find_contract_quote(chain_rows, expiry, strike, opt_type) if (chain_rows and expiry and strike is not None) else None
        quote_ts: Optional[str] = None
        if quote and quote.get("quote_ts"):
            quote_ts = str(quote["quote_ts"])
        mark_val, mark_src, out_ts, age_sec = select_mark_from_quote(
            bid=quote.get("bid") if quote else None,
            ask=quote.get("ask") if quote else None,
            last=quote.get("last") if quote else None,
            quote_ts=quote_ts,
            as_of_ts=as_of_ts,
        )
        if mark_val is not None:
            pos["mark_value"] = mark_val
            pos["mark_source"] = mark_src
            pos["quote_ts"] = out_ts
            if age_sec is not None:
                pos["mark_age_sec"] = age_sec
            # CSP: sold open, close at lower premium = profit. unrealized = (open_price - mark) * qty * 100
            pos["unrealized_pl_usd"] = round((open_price - mark_val) * qty * 100, 2)
        result.append(pos)

    return result
