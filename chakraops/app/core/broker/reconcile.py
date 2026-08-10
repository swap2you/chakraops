# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R53: Manual holdings vs broker snapshot reconcile (read-only; no auto-mutation)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from app.core.broker.models import BrokerSnapshot, EquityPosition

CLASS_MATCH = "MATCH"
CLASS_BROKER_ONLY = "BROKER_ONLY"
CLASS_MANUAL_ONLY = "MANUAL_ONLY"
CLASS_QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
CLASS_COST_BASIS_MISMATCH = "COST_BASIS_MISMATCH"
CLASS_ORDER_HOLD_DIFFERENCE = "ORDER_HOLD_DIFFERENCE"

QTY_TOLERANCE = 1e-6
COST_TOLERANCE = 0.01


@dataclass
class ManualHolding:
    symbol: str
    shares: float
    avg_cost: Optional[float] = None
    source: str = "manual"


@dataclass
class ReconcileDiff:
    symbol: str
    classification: str
    broker_qty: Optional[float] = None
    manual_qty: Optional[float] = None
    broker_avg_cost: Optional[float] = None
    manual_avg_cost: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReconcileReport:
    account_alias: str
    status: str
    diffs: List[ReconcileDiff] = field(default_factory=list)
    match_count: int = 0
    review_count: int = 0
    actions: List[str] = field(default_factory=list)
    broker_symbols: List[str] = field(default_factory=list)
    manual_symbols: List[str] = field(default_factory=list)
    auto_mutation: bool = False
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "account_alias": self.account_alias,
            "status": self.status,
            "diffs": [d.to_dict() for d in self.diffs],
            "match_count": self.match_count,
            "review_count": self.review_count,
            "actions": list(self.actions),
            "broker_symbols": list(self.broker_symbols),
            "manual_symbols": list(self.manual_symbols),
            "auto_mutation": False,
            "message": self.message,
        }


def _norm_symbol(s: str) -> str:
    return (s or "").strip().upper()


def _qty_close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= QTY_TOLERANCE


def _cost_close(a: Optional[float], b: Optional[float]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= COST_TOLERANCE


def _broker_equity_map(positions: Sequence[EquityPosition]) -> Dict[str, EquityPosition]:
    out: Dict[str, EquityPosition] = {}
    cost_num: Dict[str, float] = {}
    cost_den: Dict[str, float] = {}
    for p in positions:
        sym = _norm_symbol(p.symbol)
        if not sym:
            continue
        existing = out.get(sym)
        qty = float(p.quantity or 0.0)
        if existing is None:
            out[sym] = EquityPosition(
                symbol=sym,
                quantity=qty,
                average_cost=p.average_cost,
                market_value=p.market_value,
                side=p.side,
                meta=dict(p.meta or {}),
            )
        else:
            existing.quantity = float(existing.quantity) + qty
            if p.market_value is not None:
                existing.market_value = (existing.market_value or 0.0) + float(p.market_value)
        if p.average_cost is not None and qty:
            cost_num[sym] = cost_num.get(sym, 0.0) + float(p.average_cost) * qty
            cost_den[sym] = cost_den.get(sym, 0.0) + qty
    for sym, pos in out.items():
        den = cost_den.get(sym)
        if den and den > 0:
            pos.average_cost = cost_num[sym] / den
    return out


def reconcile_manual_vs_broker(
    *,
    account_alias: str,
    snapshot: Optional[BrokerSnapshot],
    manual_holdings: Sequence[ManualHolding],
    open_order_symbols: Optional[Sequence[str]] = None,
) -> ReconcileReport:
    """Compare manual equity holdings to broker equities. Never mutates stores."""
    actions = [
        "Review diffs; broker becomes primary live source after operator validation.",
        "No auto-mutation — apply manual-to-broker cutover only via explicit operator action.",
        "Preserve unique historical journal data; do not delete journal rows from reconcile.",
    ]
    if snapshot is None:
        return ReconcileReport(
            account_alias=account_alias,
            status="NO_BROKER",
            message="No broker snapshot available — cannot reconcile.",
            actions=actions,
            manual_symbols=sorted({_norm_symbol(h.symbol) for h in manual_holdings if _norm_symbol(h.symbol)}),
        )

    broker_map = _broker_equity_map(snapshot.equity_positions or [])
    manual_map: Dict[str, ManualHolding] = {}
    for h in manual_holdings:
        sym = _norm_symbol(h.symbol)
        if not sym:
            continue
        if sym in manual_map:
            prev = manual_map[sym]
            combined_qty = float(prev.shares) + float(h.shares)
            avg = h.avg_cost if h.avg_cost is not None else prev.avg_cost
            manual_map[sym] = ManualHolding(symbol=sym, shares=combined_qty, avg_cost=avg, source=h.source)
        else:
            manual_map[sym] = ManualHolding(
                symbol=sym,
                shares=float(h.shares or 0),
                avg_cost=h.avg_cost,
                source=h.source or "manual",
            )

    symbols = sorted(set(broker_map) | set(manual_map))
    diffs: List[ReconcileDiff] = []
    match_count = 0
    order_syms = {_norm_symbol(s) for s in (open_order_symbols or []) if _norm_symbol(s)}

    for sym in symbols:
        b = broker_map.get(sym)
        m = manual_map.get(sym)
        if b is not None and m is None:
            diffs.append(
                ReconcileDiff(
                    symbol=sym,
                    classification=CLASS_BROKER_ONLY,
                    broker_qty=float(b.quantity),
                    broker_avg_cost=b.average_cost,
                    notes="Present in broker snapshot only.",
                )
            )
            continue
        if b is None and m is not None:
            diffs.append(
                ReconcileDiff(
                    symbol=sym,
                    classification=CLASS_MANUAL_ONLY,
                    manual_qty=float(m.shares),
                    manual_avg_cost=m.avg_cost,
                    notes="Present in manual holdings only.",
                )
            )
            continue
        assert b is not None and m is not None
        if not _qty_close(b.quantity, m.shares):
            diffs.append(
                ReconcileDiff(
                    symbol=sym,
                    classification=CLASS_QUANTITY_MISMATCH,
                    broker_qty=float(b.quantity),
                    manual_qty=float(m.shares),
                    broker_avg_cost=b.average_cost,
                    manual_avg_cost=m.avg_cost,
                    notes="Quantity differs between broker and manual.",
                )
            )
            continue
        if not _cost_close(b.average_cost, m.avg_cost):
            if b.average_cost is not None or m.avg_cost is not None:
                diffs.append(
                    ReconcileDiff(
                        symbol=sym,
                        classification=CLASS_COST_BASIS_MISMATCH,
                        broker_qty=float(b.quantity),
                        manual_qty=float(m.shares),
                        broker_avg_cost=b.average_cost,
                        manual_avg_cost=m.avg_cost,
                        notes="Cost basis differs (qty matches).",
                    )
                )
                continue
        if sym in order_syms:
            diffs.append(
                ReconcileDiff(
                    symbol=sym,
                    classification=CLASS_ORDER_HOLD_DIFFERENCE,
                    broker_qty=float(b.quantity),
                    manual_qty=float(m.shares),
                    broker_avg_cost=b.average_cost,
                    manual_avg_cost=m.avg_cost,
                    notes="Open broker order may affect held or reserved shares.",
                )
            )
            continue
        match_count += 1
        diffs.append(
            ReconcileDiff(
                symbol=sym,
                classification=CLASS_MATCH,
                broker_qty=float(b.quantity),
                manual_qty=float(m.shares),
                broker_avg_cost=b.average_cost,
                manual_avg_cost=m.avg_cost,
                notes="Match.",
            )
        )

    review_count = sum(1 for d in diffs if d.classification != CLASS_MATCH)
    if not symbols:
        status = "OK"
        message = "No equity symbols on either side — empty match."
    elif review_count == 0:
        status = "OK"
        message = f"All {match_count} symbol(s) MATCH. Broker is safe as primary live source after operator ack."
    else:
        status = "REVIEW"
        message = f"{review_count} diff(s) require operator review; {match_count} MATCH."

    return ReconcileReport(
        account_alias=account_alias,
        status=status,
        diffs=diffs,
        match_count=match_count,
        review_count=review_count,
        actions=actions,
        broker_symbols=sorted(broker_map.keys()),
        manual_symbols=sorted(manual_map.keys()),
        message=message,
    )


def load_manual_holdings_for_reconcile() -> List[ManualHolding]:
    """Load default-account manual holdings from holdings_db (read-only)."""
    try:
        from app.core.accounts import holdings_db
    except ImportError:
        return []
    holdings_db.init_db()
    rows = holdings_db.list_holdings()
    out: List[ManualHolding] = []
    for r in rows:
        out.append(
            ManualHolding(
                symbol=str(r.get("symbol") or ""),
                shares=float(r.get("shares") or 0),
                avg_cost=_opt_float(r.get("avg_cost")),
                source=str(r.get("source") or "manual"),
            )
        )
    return out


def _opt_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
