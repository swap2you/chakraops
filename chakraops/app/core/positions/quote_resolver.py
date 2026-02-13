# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Resolve bid/ask for a specific contract from chain rows. Safe float comparison."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

STRIKE_TOLERANCE = 1e-6


def _strike_eq(a: Any, b: Any, tol: float = STRIKE_TOLERANCE) -> bool:
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def _norm_exp(value: Any) -> Optional[str]:
    """Normalize expiration to YYYY-MM-DD string."""
    if value is None:
        return None
    s = str(value).strip()[:10]
    return s if len(s) == 10 else None


def _row_option_type(row: Dict[str, Any]) -> str:
    """Return PUT or CALL from row."""
    ot = (row.get("putCall") or row.get("optionType") or row.get("option_type") or "").strip().upper()
    if ot in ("P", "PUT", "PUTS"):
        return "PUT"
    if ot in ("C", "CALL", "CALLS"):
        return "CALL"
    return ""


def find_contract_quote(
    chain_rows: List[Dict[str, Any]],
    expiration: Any,
    strike: Any,
    option_type: str,
    strike_tol: float = STRIKE_TOLERANCE,
) -> Optional[Dict[str, Any]]:
    """
    Find bid/ask for the contract matching expiration, strike, option_type.
    Returns {"bid": float, "ask": float} (values may be None) or None if no matching row.
    Handles strike float/int comparison with tolerance.
    """
    if not chain_rows:
        return None
    exp_norm = _norm_exp(expiration)
    if not exp_norm:
        return None
    try:
        strike_f = float(strike)
    except (TypeError, ValueError):
        return None
    ot_upper = (option_type or "PUT").strip().upper()
    if ot_upper not in ("PUT", "CALL"):
        ot_upper = "PUT"

    for row in chain_rows:
        row_exp = _norm_exp(row.get("exp") or row.get("expirDate") or row.get("expiration"))
        if row_exp != exp_norm:
            continue
        if not _strike_eq(row.get("strike"), strike_f, strike_tol):
            continue
        row_ot = _row_option_type(row)
        if row_ot != ot_upper:
            continue
        bid = row.get("bid") if row.get("bid") is not None else row.get("bidPrice")
        ask = row.get("ask") if row.get("ask") is not None else row.get("askPrice")
        if bid is None and ask is None:
            continue
        try:
            b = float(bid) if bid is not None else None
            a = float(ask) if ask is not None else None
        except (TypeError, ValueError):
            continue
        return {"bid": b, "ask": a}
    return None
