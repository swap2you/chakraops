# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 19.0: Wheel policy evaluation — one position per symbol, DTE range, IV rank."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.positions.lifecycle import compute_dte


def _get_symbol_iv_rank(latest_decision: Any, symbol: str) -> Optional[float]:
    """Extract IV rank for symbol from decision artifact if available."""
    if not latest_decision:
        return None
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    # diagnostics_by_symbol may have options.iv_rank or similar
    if hasattr(latest_decision, "diagnostics_by_symbol"):
        diag = latest_decision.diagnostics_by_symbol.get(sym)
        if diag and hasattr(diag, "options") and isinstance(getattr(diag, "options", None), dict):
            iv = (diag.options or {}).get("iv_rank")
            if iv is not None:
                try:
                    return float(iv)
                except (TypeError, ValueError):
                    pass
    # Symbol row might have iv_rank on SymbolEvalSummary (if we add it later)
    if hasattr(latest_decision, "symbols") and latest_decision.symbols:
        for s in latest_decision.symbols:
            if (getattr(s, "symbol", None) or "").strip().upper() == sym:
                iv = getattr(s, "iv_rank", None)
                if iv is not None:
                    try:
                        return float(iv)
                    except (TypeError, ValueError):
                        pass
                break
    return None


def evaluate_wheel_policy(
    account: Any,
    symbol: str,
    wheel_state: Dict[str, Any],
    latest_decision: Optional[Any],
    open_positions: List[Any],
    *,
    expiration: Optional[str] = None,
    contract_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate wheel policy for opening/adding a position in symbol.
    Returns {allowed: bool, blocked_by: []}.
    Checks: one position per symbol (when wheel_one_position_per_symbol), DTE range, min IV rank.
    """
    blocked_by: List[str] = []
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"allowed": False, "blocked_by": ["symbol required"]}

    one_per = getattr(account, "wheel_one_position_per_symbol", True)
    min_dte = int(getattr(account, "wheel_min_dte", 21))
    max_dte = int(getattr(account, "wheel_max_dte", 60))
    min_iv = getattr(account, "wheel_min_iv_rank", None)
    if min_iv is not None:
        try:
            min_iv = float(min_iv)
        except (TypeError, ValueError):
            min_iv = None

    if one_per:
        open_for_symbol = [
            p for p in open_positions
            if (getattr(p, "symbol", "") or "").strip().upper() == symbol
            and (getattr(p, "status", "") or "").upper() in ("OPEN", "PARTIAL_EXIT")
        ]
        if open_for_symbol:
            blocked_by.append("wheel_one_position_per_symbol")

    if expiration is not None and (min_dte is not None or max_dte is not None):
        dte = compute_dte(expiration)
        if dte is not None:
            if min_dte is not None and dte < min_dte:
                blocked_by.append(f"wheel_min_dte({dte}<{min_dte})")
            if max_dte is not None and dte > max_dte:
                blocked_by.append(f"wheel_max_dte({dte}>{max_dte})")

    if min_iv is not None and min_iv > 0:
        iv_rank = _get_symbol_iv_rank(latest_decision, symbol)
        if iv_rank is not None and iv_rank < min_iv:
            blocked_by.append(f"wheel_min_iv_rank({iv_rank:.1f}<{min_iv})")

    return {"allowed": len(blocked_by) == 0, "blocked_by": blocked_by}
