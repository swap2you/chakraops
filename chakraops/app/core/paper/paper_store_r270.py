# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.0: Paper trading — simulated fills and positions. SQLite under DATA_DIR. Deterministic P/L. No FAIL_/WARN_."""

from __future__ import annotations

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

INSTRUMENT_SHARES = "SHARES"
INSTRUMENT_OPTION = "OPTION"
STRATEGY_CSP = "CSP"
STRATEGY_CC = "CC"
STRATEGY_SHARES = "SHARES"
STATUS_OPEN = "OPEN"
STATUS_CLOSED = "CLOSED"
ACTION_OPEN = "OPEN"
ACTION_CLOSE = "CLOSE"


def _paper_db_path() -> Path:
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "paper.db"
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "paper.db"


def set_paper_db_path(path: Path) -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_paper_db_path() -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_paper_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_paper_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS paper_positions (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        instrument_type TEXT NOT NULL,
        strategy TEXT NOT NULL,
        side TEXT NOT NULL DEFAULT 'LONG',
        qty INTEGER NOT NULL,
        contract_key TEXT,
        expiry TEXT,
        strike REAL,
        right TEXT,
        open_ts TEXT NOT NULL,
        open_price REAL NOT NULL,
        open_fees REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'OPEN',
        close_ts TEXT,
        close_price REAL,
        close_fees REAL,
        realized_pl REAL,
        notes TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_paper_positions_status ON paper_positions(status);
    CREATE INDEX IF NOT EXISTS idx_paper_positions_symbol ON paper_positions(symbol);
    CREATE INDEX IF NOT EXISTS idx_paper_positions_strategy ON paper_positions(strategy);
    CREATE INDEX IF NOT EXISTS idx_paper_positions_open_ts ON paper_positions(open_ts DESC);

    CREATE TABLE IF NOT EXISTS paper_fills (
        id TEXT PRIMARY KEY,
        position_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        action TEXT NOT NULL,
        qty INTEGER NOT NULL,
        price REAL NOT NULL,
        fees REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_paper_fills_position ON paper_fills(position_id);
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


def _trade_date_from_ts(ts: str) -> str:
    if not ts or len(ts) < 10:
        return (datetime.now(timezone.utc).date()).isoformat()
    return ts[:10]


def paper_execute_open(
    symbol: str,
    strategy: str,
    qty: int,
    open_price: float,
    open_fees: float = 0,
    contract_key: Optional[str] = None,
    expiry: Optional[str] = None,
    strike: Optional[float] = None,
    right: Optional[str] = None,
    ts: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Create open paper position and fill. Returns position record."""
    init_paper_db()
    symbol = (symbol or "").strip().upper()
    strategy = (strategy or "SHARES").strip().upper()
    if strategy == STRATEGY_SHARES:
        instrument_type = INSTRUMENT_SHARES
    else:
        instrument_type = INSTRUMENT_OPTION
    now = ts or _now_iso()
    pos_id = str(uuid.uuid4())
    fill_id = str(uuid.uuid4())
    open_fees_val = float(open_fees) if open_fees is not None else 0.0
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO paper_positions (
                    id, symbol, instrument_type, strategy, side, qty, contract_key, expiry, strike, right,
                    open_ts, open_price, open_fees, status, notes
                ) VALUES (?, ?, ?, ?, 'LONG', ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', ?)""",
                (
                    pos_id, symbol, instrument_type, strategy,
                    int(qty), (contract_key or "").strip() or None, (expiry or "").strip()[:10] or None,
                    strike, (right or "").strip() or None,
                    now, float(open_price), open_fees_val,
                    (notes or "").strip()[:500] or None,
                ),
            )
            conn.execute(
                """INSERT INTO paper_fills (id, position_id, ts, action, qty, price, fees)
                   VALUES (?, ?, ?, 'OPEN', ?, ?, ?)""",
                (fill_id, pos_id, now, int(qty), float(open_price), open_fees_val),
            )
            conn.commit()
        finally:
            conn.close()
    return paper_get_position(pos_id) or {}


def paper_execute_close(
    position_id: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    contract_key: Optional[str] = None,
    close_price: float = 0,
    close_fees: float = 0,
    ts: Optional[str] = None,
) -> Dict[str, Any]:
    """Close an open paper position; compute realized_pl; create close fill. Returns closed position."""
    init_paper_db()
    now = ts or _now_iso()
    close_fees_val = float(close_fees) if close_fees is not None else 0.0

    if position_id:
        pos = paper_get_position(position_id)
    else:
        positions = paper_list_positions(status=STATUS_OPEN, symbol=symbol or "", strategy=strategy or "")
        if contract_key:
            positions = [p for p in positions if (p.get("contract_key") or "").strip() == (contract_key or "").strip()]
        if not positions:
            raise ValueError("No matching open position")
        pos = positions[0]
        position_id = pos["id"]

    if not pos or (pos.get("status") or "").upper() != STATUS_OPEN:
        raise ValueError("Position not found or already closed")

    qty = int(pos.get("qty") or 0)
    open_price = float(pos.get("open_price") or 0)
    open_fees_val = float(pos.get("open_fees") or 0)
    instrument_type = (pos.get("instrument_type") or INSTRUMENT_SHARES).upper()

    if instrument_type == INSTRUMENT_SHARES:
        realized_pl = (float(close_price) - open_price) * qty - open_fees_val - close_fees_val
    else:
        realized_pl = (open_price - float(close_price)) * qty * 100 - open_fees_val - close_fees_val

    fill_id = str(uuid.uuid4())
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """UPDATE paper_positions SET status = 'CLOSED', close_ts = ?, close_price = ?, close_fees = ?, realized_pl = ?
                   WHERE id = ?""",
                (now, float(close_price), close_fees_val, round(realized_pl, 2), position_id),
            )
            conn.execute(
                """INSERT INTO paper_fills (id, position_id, ts, action, qty, price, fees)
                   VALUES (?, ?, ?, 'CLOSE', ?, ?, ?)""",
                (fill_id, position_id, now, qty, float(close_price), close_fees_val),
            )
            conn.commit()
        finally:
            conn.close()
    return paper_get_position(position_id) or {}


def paper_get_position(position_id: str) -> Optional[Dict[str, Any]]:
    init_paper_db()
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM paper_positions WHERE id = ?", (position_id.strip(),)).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def paper_list_positions(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    init_paper_db()
    conditions: List[str] = []
    params: List[Any] = []
    if status:
        conditions.append("status = ?")
        params.append((status or "").strip().upper())
    if symbol:
        conditions.append("symbol = ?")
        params.append((symbol or "").strip().upper())
    if strategy:
        conditions.append("strategy = ?")
        params.append((strategy or "").strip().upper())
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM paper_positions{where} ORDER BY open_ts DESC LIMIT ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def paper_summary_by_month(month: str) -> Dict[str, Any]:
    """month = YYYY-MM. Returns realized_pl, trade_count, win_count, win_rate, fees_total, by_strategy."""
    init_paper_db()
    if len(month) != 7 or month[4] != "-":
        return {"month": month, "realized_pl": 0, "trade_count": 0, "win_count": 0, "win_rate": None, "fees_total": 0, "by_strategy": {}}
    prefix = month + "%"
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT * FROM paper_positions WHERE status = 'CLOSED' AND close_ts LIKE ?""",
                (prefix,),
            ).fetchall()
            closed = [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
    total_pl = 0.0
    fees_total = 0.0
    by_strategy: Dict[str, float] = {}
    for p in closed:
        pl = p.get("realized_pl")
        if pl is not None:
            total_pl += float(pl)
        strat = (p.get("strategy") or "SHARES").upper()
        by_strategy[strat] = by_strategy.get(strat, 0.0) + (float(pl) if pl is not None else 0.0)
        ofee = p.get("open_fees") or 0
        cfee = p.get("close_fees") or 0
        fees_total += float(ofee) + float(cfee)
    with_pl = [p for p in closed if p.get("realized_pl") is not None]
    win_count = sum(1 for p in with_pl if (p.get("realized_pl") or 0) > 0)
    trade_count = len(with_pl)
    win_rate = (win_count / trade_count * 100) if trade_count else None
    return {
        "month": month,
        "realized_pl": round(total_pl, 2),
        "trade_count": trade_count,
        "win_count": win_count,
        "win_rate": round(win_rate, 1) if win_rate is not None else None,
        "fees_total": round(fees_total, 2),
        "by_strategy": {k: round(v, 2) for k, v in by_strategy.items()},
    }
