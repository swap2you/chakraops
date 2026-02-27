# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.5: SQLite-backed trade journal (manual executions). DB at data/journal.db; not under out/."""

from __future__ import annotations

import csv
import io
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_PATH: Optional[Path] = None


def _journal_db_path() -> Path:
    """Journal DB under data/ (not out/). Repo-relative from app/core/journal/."""
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "journal.db"


def set_journal_db_path(path: Path) -> None:
    """Override DB path (for tests)."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_journal_db_path() -> None:
    """Reset to default path."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _get_conn() -> sqlite3.Connection:
    path = _journal_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_journal_db() -> None:
    """Create journal_entries table if not exist. Safe to call repeatedly."""
    sql = """
    CREATE TABLE IF NOT EXISTS journal_entries (
        id TEXT PRIMARY KEY,
        created_ts TEXT NOT NULL,
        trade_date TEXT NOT NULL,
        as_of_ts TEXT,
        symbol TEXT NOT NULL,
        strategy TEXT NOT NULL,
        action TEXT NOT NULL,
        qty REAL NOT NULL DEFAULT 0,
        price REAL,
        premium REAL,
        fees REAL,
        contract_key TEXT,
        expiry TEXT,
        strike REAL,
        right TEXT,
        notes TEXT,
        tags TEXT,
        realized_pl REAL,
        link_id TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_journal_trade_date ON journal_entries(trade_date);
    CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_entries(symbol);
    CREATE INDEX IF NOT EXISTS idx_journal_strategy ON journal_entries(strategy);
    CREATE INDEX IF NOT EXISTS idx_journal_created_ts ON journal_entries(created_ts DESC);
    """
    with _LOCK:
        conn = _get_conn()
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row) if row else {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def journal_create(
    trade_date: str,
    symbol: str,
    strategy: str,
    action: str,
    qty: float,
    price: Optional[float] = None,
    premium: Optional[float] = None,
    fees: Optional[float] = None,
    contract_key: Optional[str] = None,
    expiry: Optional[str] = None,
    strike: Optional[float] = None,
    right: Optional[str] = None,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
    realized_pl: Optional[float] = None,
    link_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert one journal entry. Returns created record."""
    init_journal_db()
    entry_id = str(uuid.uuid4())
    created_ts = _now_iso()
    as_of_ts = created_ts
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO journal_entries (
                    id, created_ts, trade_date, as_of_ts, symbol, strategy, action,
                    qty, price, premium, fees, contract_key, expiry, strike, right,
                    notes, tags, realized_pl, link_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id, created_ts, trade_date, as_of_ts, symbol.strip().upper(), strategy, action,
                    qty, price, premium, fees, (contract_key or "").strip() or None,
                    (expiry or "").strip() or None, strike, (right or "").strip() or None,
                    (notes or "").strip()[:2000] or None, (tags or "").strip()[:500] or None,
                    realized_pl, (link_id or "").strip() or None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return journal_get(entry_id) or {}


def journal_get(entry_id: str) -> Optional[Dict[str, Any]]:
    """Get one entry by id."""
    init_journal_db()
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM journal_entries WHERE id = ?", (entry_id.strip(),)).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def journal_list(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List entries ordered by created_ts desc. All params optional; use ? placeholders."""
    init_journal_db()
    conditions: List[str] = []
    params: List[Any] = []
    if from_date:
        conditions.append("trade_date >= ?")
        params.append(from_date)
    if to_date:
        conditions.append("trade_date <= ?")
        params.append(to_date)
    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol.strip().upper())
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy.strip().upper())
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM journal_entries{where} ORDER BY created_ts DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def journal_update(
    entry_id: str,
    notes: Optional[str] = None,
    tags: Optional[str] = None,
    fees: Optional[float] = None,
    trade_date: Optional[str] = None,
    qty: Optional[float] = None,
    price: Optional[float] = None,
    premium: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Update safe fields. Returns updated record or None if not found."""
    init_journal_db()
    updates: List[str] = []
    params: List[Any] = []
    if notes is not None:
        updates.append("notes = ?")
        params.append((notes or "").strip()[:2000] or None)
    if tags is not None:
        updates.append("tags = ?")
        params.append((tags or "").strip()[:500] or None)
    if fees is not None:
        updates.append("fees = ?")
        params.append(fees)
    if trade_date is not None:
        updates.append("trade_date = ?")
        params.append(trade_date)
    if qty is not None:
        updates.append("qty = ?")
        params.append(qty)
    if price is not None:
        updates.append("price = ?")
        params.append(price)
    if premium is not None:
        updates.append("premium = ?")
        params.append(premium)
    if not updates:
        return journal_get(entry_id)
    params.append(entry_id.strip())
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                f"UPDATE journal_entries SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
    return journal_get(entry_id)


def journal_export_csv(from_date: str, to_date: str) -> str:
    """Export entries in date range as CSV string. Safe columns only."""
    init_journal_db()
    rows = journal_list(from_date=from_date, to_date=to_date, limit=10000, offset=0)
    out = io.StringIO()
    if not rows:
        w = csv.writer(out)
        w.writerow(["id", "created_ts", "trade_date", "symbol", "strategy", "action", "qty", "price", "premium", "fees", "contract_key", "notes", "tags", "realized_pl", "link_id"])
        return out.getvalue()
    keys = list(rows[0].keys())
    writer = csv.DictWriter(out, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return out.getvalue()


def journal_monthly_aggregate(month: str) -> Dict[str, Any]:
    """month = YYYY-MM. Returns total_realized_pl, by_strategy, trade_count, win_count, loss_count, win_rate, avg_hold_days, top_winners, top_losers, fees_total."""
    init_journal_db()
    from_ym = f"{month}-01"
    to_ym = f"{month}-31"
    if len(month) == 7:
        import calendar
        y, m = int(month[:4]), int(month[5:7])
        last = calendar.monthrange(y, m)[1]
        to_ym = f"{month}-{last:02d}"
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, symbol, strategy, action, qty, price, premium, fees, realized_pl, trade_date, link_id
                   FROM journal_entries WHERE trade_date >= ? AND trade_date <= ? ORDER BY created_ts""",
                (from_ym, to_ym),
            ).fetchall()
            entries = [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
    total_pl = 0.0
    by_strategy: Dict[str, float] = {}
    fees_total = 0.0
    with_pl: List[Dict[str, Any]] = []
    for e in entries:
        pl = e.get("realized_pl")
        if pl is not None:
            total_pl += float(pl)
            with_pl.append(e)
        strat = (e.get("strategy") or "SHARES").upper()
        by_strategy[strat] = by_strategy.get(strat, 0.0) + (float(pl) if pl is not None else 0.0)
        f = e.get("fees")
        if f is not None:
            fees_total += float(f)
    win_count = sum(1 for e in with_pl if (e.get("realized_pl") or 0) > 0)
    loss_count = sum(1 for e in with_pl if (e.get("realized_pl") or 0) < 0)
    trade_count = len(with_pl)
    win_rate = (win_count / trade_count * 100) if trade_count else 0.0
    sorted_pl = sorted(with_pl, key=lambda x: float(x.get("realized_pl") or 0), reverse=True)
    top_winners = [{"symbol": e.get("symbol"), "realized_pl": e.get("realized_pl"), "strategy": e.get("strategy")} for e in sorted_pl[:5]]
    top_losers = [{"symbol": e.get("symbol"), "realized_pl": e.get("realized_pl"), "strategy": e.get("strategy")} for e in sorted_pl[-5:][::-1]]
    return {
        "month": month,
        "total_realized_pl": round(total_pl, 2),
        "by_strategy": {k: round(v, 2) for k, v in by_strategy.items()},
        "trade_count": trade_count,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 1),
        "avg_hold_days": None,
        "top_winners": top_winners,
        "top_losers": top_losers,
        "fees_total": round(fees_total, 2),
    }
