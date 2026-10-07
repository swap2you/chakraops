# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CSV export for trade journal. Stable column order for tests."""

from __future__ import annotations

import csv
import io
from typing import List, Optional

from app.core.journal.models import Trade
from app.core.journal.store import list_trades, get_trade, compute_trade_derived


# Stable column order for CSV (single-trade and multi-trade)
TRADE_CSV_COLUMNS = [
    "trade_id",
    "symbol",
    "strategy",
    "opened_at",
    "expiry",
    "strike",
    "side",
    "contracts",
    "remaining_qty",
    "entry_mid_est",
    "avg_entry",
    "avg_exit",
    "realized_pnl",
    "run_id",
    "stop_level",
    "target_levels",
    "notes",
]


def _trade_row(t: Trade) -> List[str]:
    """One trade as a list of string values in TRADE_CSV_COLUMNS order."""
    target_str = "|".join(str(x) for x in (t.target_levels or []))
    return [
        t.trade_id,
        t.symbol,
        t.strategy,
        t.opened_at,
        t.expiry or "",
        str(t.strike) if t.strike is not None else "",
        t.side,
        str(t.contracts),
        str(t.remaining_qty),
        str(t.entry_mid_est) if t.entry_mid_est is not None else "",
        str(t.avg_entry) if t.avg_entry is not None else "",
        str(t.avg_exit) if t.avg_exit is not None else "",
        str(t.realized_pnl) if t.realized_pnl is not None else "",
        t.run_id or "",
        str(t.stop_level) if t.stop_level is not None else "",
        target_str,
        (t.notes or "").replace("\r", " ").replace("\n", " "),
    ]


def export_trades_csv(limit: int = 500) -> str:
    """Export all trades to CSV string. Columns in TRADE_CSV_COLUMNS order."""
    trades = list_trades(limit=limit)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TRADE_CSV_COLUMNS)
    for t in trades:
        w.writerow(_trade_row(t))
    return buf.getvalue()


def export_trade_csv(trade_id: str) -> Optional[str]:
    """Export a single trade to CSV string."""
    t = get_trade(trade_id)
    if not t:
        return None
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(TRADE_CSV_COLUMNS)
    w.writerow(_trade_row(t))
    return buf.getvalue()
