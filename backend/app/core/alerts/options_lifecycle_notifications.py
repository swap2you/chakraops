# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.3.1: Emit options lifecycle notifications during/after eval run (decoupled from GET /api/ui/action-needed)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _emit_for_position(
    symbol: str,
    position: Any,
    spot: Optional[float],
    quote: Optional[Dict[str, Any]],
    as_of_ts: Optional[float],
    quote_ts: Optional[str],
) -> None:
    """Compute lifecycle for one position and append notification on transition (dedupe in store)."""
    try:
        from app.core.lifecycle.position_lifecycle_r243 import (
            RECOMMENDED_BY_R253,
            compute_position_lifecycle,
        )
        from app.api.notifications_store import (
            maybe_append_options_lifecycle_notification,
            OPTIONS_PROFIT_TARGET_HIT,
            OPTIONS_ROLL_WINDOW,
            OPTIONS_ASSIGNMENT_RISK,
        )
        import time as _time
        ckey = getattr(position, "contract_key", None) or getattr(position, "position_id", "")
        if not ckey:
            return
        as_of_str = quote_ts or datetime.now(timezone.utc).isoformat()
        lc = compute_position_lifecycle(
            position,
            spot=spot,
            bid=quote.get("bid") if quote else None,
            ask=quote.get("ask") if quote else None,
            last=quote.get("last") if quote else None,
            quote_ts=quote_ts,
            as_of_ts=as_of_ts or _time.time(),
            recommended_by=RECOMMENDED_BY_R253,
        )
        expiry = getattr(position, "expiration", None) or getattr(position, "expiry", None)
        strike = getattr(position, "strike", None)
        rec_code = lc.get("recommended_action_code")
        if rec_code and rec_code not in ("CLOSE", "ROLL", "HOLD"):
            rec_code = None
        payload = {
            "symbol": symbol,
            "contract_key": ckey,
            "expiry": expiry,
            "strike": strike,
            "right": "PUT" if (getattr(position, "strategy", "") or "").upper() == "CSP" else "CALL",
            "dte": lc.get("dte"),
            "profit_pct": lc.get("pct_max_profit"),
            "mark_value": lc.get("mark_value"),
            "as_of_ts": as_of_str,
        }
        if rec_code:
            payload["recommended_action_code"] = rec_code
        if rec_code == "CLOSE" and (lc.get("pct_max_profit") or 0) >= 50:
            maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_PROFIT_TARGET_HIT, payload)
        elif rec_code == "CLOSE" and (lc.get("assignment_risk") or {}).get("active"):
            maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_ASSIGNMENT_RISK, payload)
        elif rec_code == "ROLL":
            maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_ROLL_WINDOW, payload)
    except Exception as e:
        logger.debug("[OPTIONS_LIFECYCLE] Emit skip for %s: %s", symbol, e)


def emit_options_lifecycle_notifications_from_artifact(artifact: Any) -> None:
    """
    R25.3.1: After eval run that produced artifact (v2), emit options lifecycle notifications
    for open tracked positions. Uses artifact for candidates + spot. Dedupe in notifications_store.
    """
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.quote_resolver import find_contract_quote
        import time as _time
        symbols_list = getattr(artifact, "symbols", []) or []
        candidates_by_symbol = getattr(artifact, "candidates_by_symbol", {}) or {}
        by_sym: Dict[str, Any] = {}
        for s in symbols_list:
            sym = (getattr(s, "symbol", "") or "").strip().upper()
            if sym:
                by_sym[sym] = s
        open_pos = list_positions(status="OPEN", symbol=None, exclude_test=True)
        opt_positions = [p for p in open_pos if (getattr(p, "strategy", "") or "").upper() in ("CSP", "CC")]
        as_of_ts = _time.time()
        for pos in opt_positions:
            sym = (getattr(pos, "symbol", "") or "").strip().upper()
            if not sym or sym not in by_sym:
                continue
            summary = by_sym[sym]
            spot = getattr(summary, "price", None) or getattr(summary, "underlying_price", None)
            if spot is not None:
                spot = float(spot)
            chain_rows = candidates_by_symbol.get(sym) or []
            c_dicts = []
            for c in chain_rows:
                d = c.to_dict() if hasattr(c, "to_dict") else (c if isinstance(c, dict) else {})
                if d:
                    if d.get("expiration") is None and d.get("expiry") is not None:
                        d = {**d, "expiration": d["expiry"]}
                    if not d.get("option_type") and not d.get("putCall"):
                        d = {**d, "option_type": "PUT" if (d.get("strategy") or "").upper() == "CSP" else "CALL"}
                c_dicts.append(d)
            expiry = getattr(pos, "expiration", None) or getattr(pos, "expiry", None)
            strike = getattr(pos, "strike", None)
            opt_type = "PUT" if (getattr(pos, "strategy", "") or "").upper() == "CSP" else "CALL"
            quote = find_contract_quote(c_dicts, expiry, strike, opt_type) if c_dicts and expiry and strike is not None else None
            quote_ts = str(quote["quote_ts"]) if quote and quote.get("quote_ts") else None
            _emit_for_position(sym, pos, spot, quote, as_of_ts, quote_ts)
    except Exception as e:
        logger.warning("[OPTIONS_LIFECYCLE] emit_from_artifact failed: %s", e)


def emit_options_lifecycle_notifications_from_run(run: Any) -> None:
    """
    R25.3.1: After scheduled eval run (EvaluationRunFull), emit options lifecycle notifications
    for open tracked positions. Uses run.symbols for spot and selected_candidates as chain. Dedupe in store.
    """
    try:
        from app.core.positions.service import list_positions
        from app.core.positions.quote_resolver import find_contract_quote
        import time as _time
        symbols_data = getattr(run, "symbols", []) or []
        by_sym: Dict[str, Dict[str, Any]] = {}
        for s in symbols_data:
            if isinstance(s, dict):
                sym = (s.get("symbol") or "").strip().upper()
            else:
                sym = (getattr(s, "symbol", "") or "").strip().upper()
            if sym:
                by_sym[sym] = s if isinstance(s, dict) else (getattr(s, "__dict__", None) or {})
        open_pos = list_positions(status="OPEN", symbol=None, exclude_test=True)
        opt_positions = [p for p in open_pos if (getattr(p, "strategy", "") or "").upper() in ("CSP", "CC")]
        as_of_ts = _time.time()
        for pos in opt_positions:
            sym = (getattr(pos, "symbol", "") or "").strip().upper()
            if not sym or sym not in by_sym:
                continue
            sym_data = by_sym[sym]
            spot = sym_data.get("price") if isinstance(sym_data, dict) else getattr(sym_data, "price", None)
            if spot is not None:
                spot = float(spot)
            selected = sym_data.get("selected_candidates", []) if isinstance(sym_data, dict) else getattr(sym_data, "selected_candidates", [])
            chain_rows = [c if isinstance(c, dict) else (getattr(c, "to_dict", lambda: c)() if callable(getattr(c, "to_dict", None)) else c) for c in selected]
            expiry = getattr(pos, "expiration", None) or getattr(pos, "expiry", None)
            strike = getattr(pos, "strike", None)
            opt_type = "PUT" if (getattr(pos, "strategy", "") or "").upper() == "CSP" else "CALL"
            quote = find_contract_quote(chain_rows, expiry, strike, opt_type) if chain_rows and expiry and strike is not None else None
            quote_ts = str(quote["quote_ts"]) if quote and quote.get("quote_ts") else None
            _emit_for_position(sym, pos, spot, quote, as_of_ts, quote_ts)
    except Exception as e:
        logger.warning("[OPTIONS_LIFECYCLE] emit_from_run failed: %s", e)
