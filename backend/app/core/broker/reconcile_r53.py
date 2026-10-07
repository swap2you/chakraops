# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R53: reconcile manual holdings vs broker snapshot (no auto-mutation)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def classify_holding(
    *,
    symbol: str,
    manual_qty: Optional[float],
    broker_qty: Optional[float],
    manual_cost: Optional[float] = None,
    broker_cost: Optional[float] = None,
) -> str:
    sym = (symbol or "").upper().strip()
    if not sym:
        return "INVALID"
    m = manual_qty
    b = broker_qty
    if m is None and b is None:
        return "INVALID"
    if m is None and b is not None:
        return "BROKER_ONLY"
    if b is None and m is not None:
        return "MANUAL_ONLY"
    assert m is not None and b is not None
    if abs(m - b) > 1e-6:
        return "QUANTITY_MISMATCH"
    if manual_cost is not None and broker_cost is not None and abs(manual_cost - broker_cost) > 0.02:
        return "COST_BASIS_MISMATCH"
    return "MATCH"


def reconcile_manual_vs_broker(
    manual_holdings: List[Dict[str, Any]],
    broker_equities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare manual vs broker equity rows. Never mutates stores."""
    manual_map: Dict[str, Dict[str, Any]] = {}
    for h in manual_holdings or []:
        if not isinstance(h, dict):
            continue
        sym = str(h.get("symbol") or "").upper().strip()
        if not sym:
            continue
        manual_map[sym] = h

    broker_map: Dict[str, Dict[str, Any]] = {}
    for p in broker_equities or []:
        if not isinstance(p, dict):
            continue
        sym = str(p.get("symbol") or "").upper().strip()
        if not sym:
            continue
        broker_map[sym] = p

    symbols = sorted(set(manual_map) | set(broker_map))
    rows: List[Dict[str, Any]] = []
    for sym in symbols:
        m = manual_map.get(sym)
        b = broker_map.get(sym)
        m_qty = _f(m.get("shares") if m else None)
        if m_qty is None and m:
            m_qty = _f(m.get("quantity"))
        b_qty = _f(b.get("quantity") if b else None)
        m_cost = _f(m.get("avg_cost") if m else None)
        b_cost = _f(b.get("average_cost") if b else None)
        classification = classify_holding(
            symbol=sym,
            manual_qty=m_qty,
            broker_qty=b_qty,
            manual_cost=m_cost,
            broker_cost=b_cost,
        )
        rows.append(
            {
                "symbol": sym,
                "classification": classification,
                "manual_qty": m_qty,
                "broker_qty": b_qty,
                "manual_cost": m_cost,
                "broker_cost": b_cost,
            }
        )

    return {
        "manual_only": True,
        "trade_execution": False,
        "auto_mutation": False,
        "row_count": len(rows),
        "rows": rows,
        "message": "Reconciliation is advisory. Operator must explicitly migrate; no auto-mutation.",
    }


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
