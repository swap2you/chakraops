# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.6: Universe change audit log (SQLite). Propose add/remove, apply, history. DB at data/universe_admin.db."""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_PATH: Optional[Path] = None

ACTOR_DEFAULT = "self"
ACTIONS = ("PROPOSE_ADD", "PROPOSE_REMOVE", "APPLY_ADD", "APPLY_REMOVE")
STATUSES = ("OPEN", "APPLIED", "CANCELLED")
REASON_CODES_ADD = ("LIQUIDITY_ADD", "PRICE_FLOOR_ADD", "OPTIONS_LIQUIDITY_ADD", "SECTOR_BALANCE_ADD", "OTHER_ADD")
REASON_CODES_REMOVE = ("ILLIQUIDITY_REMOVE", "VOLATILITY_REMOVE", "REPEATED_FAILURES_REMOVE", "DATA_UNAVAILABLE_REMOVE", "OTHER_REMOVE")


def _db_path() -> Path:
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "universe_admin.db"


def set_universe_admin_db_path(path: Path) -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_universe_admin_db_path() -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_universe_admin_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS universe_change_log (
        id TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        symbol TEXT NOT NULL,
        reason_code TEXT,
        notes TEXT,
        status TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_ucl_ts ON universe_change_log(ts DESC);
    CREATE INDEX IF NOT EXISTS idx_ucl_symbol ON universe_change_log(symbol);
    CREATE INDEX IF NOT EXISTS idx_ucl_status ON universe_change_log(status);
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


def create_proposal(action: str, symbol: str, reason_code: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Create PROPOSE_ADD or PROPOSE_REMOVE. Returns record."""
    if action not in ("PROPOSE_ADD", "PROPOSE_REMOVE"):
        raise ValueError("action must be PROPOSE_ADD or PROPOSE_REMOVE")
    init_universe_admin_db()
    entry_id = str(uuid.uuid4())
    ts = _now_iso()
    actor = ACTOR_DEFAULT
    status = "OPEN"
    reason_code = (reason_code or "").strip() or None
    notes = (notes or "").strip()[:1000] or None
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol required")
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO universe_change_log (id, ts, actor, action, symbol, reason_code, notes, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, ts, actor, action, symbol, reason_code, notes, status),
            )
            conn.commit()
        finally:
            conn.close()
    return {"id": entry_id, "ts": ts, "actor": actor, "action": action, "symbol": symbol, "reason_code": reason_code, "notes": notes, "status": status}


def list_history(limit: int = 50, offset: int = 0, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List log entries by ts desc."""
    init_universe_admin_db()
    params: List[Any] = []
    where = ""
    if status:
        where = " WHERE status = ?"
        params.append(status)
    params.extend([limit, offset])
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM universe_change_log{where} ORDER BY ts DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def get_proposal(proposal_id: str) -> Optional[Dict[str, Any]]:
    init_universe_admin_db()
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM universe_change_log WHERE id = ?", (proposal_id.strip(),)).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def mark_applied(proposal_id: str) -> bool:
    """Set status to APPLIED for proposal. Returns True if updated."""
    init_universe_admin_db()
    with _LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute("UPDATE universe_change_log SET status = ? WHERE id = ? AND status = ?", ("APPLIED", proposal_id.strip(), "OPEN"))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def log_apply(action: str, symbol: str, reason_code: Optional[str] = None, notes: Optional[str] = None) -> Dict[str, Any]:
    """Log APPLY_ADD or APPLY_REMOVE (no overlay change here; caller does add_symbol/remove_symbol)."""
    if action not in ("APPLY_ADD", "APPLY_REMOVE"):
        raise ValueError("action must be APPLY_ADD or APPLY_REMOVE")
    init_universe_admin_db()
    entry_id = str(uuid.uuid4())
    ts = _now_iso()
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO universe_change_log (id, ts, actor, action, symbol, reason_code, notes, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (entry_id, ts, ACTOR_DEFAULT, action, (symbol or "").strip().upper(), (reason_code or "").strip() or None, (notes or "").strip()[:1000] or None, "APPLIED"),
            )
            conn.commit()
        finally:
            conn.close()
    return {"id": entry_id, "ts": ts, "action": action, "symbol": (symbol or "").strip().upper(), "status": "APPLIED"}


def recent_changes_days(days: int = 30) -> tuple[List[str], List[str]]:
    """Return (added_symbols, removed_symbols) in last N days (by APPLY_ADD/APPLY_REMOVE)."""
    init_universe_admin_db()
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    added: List[str] = []
    removed: List[str] = []
    with _LOCK:
        conn = _get_conn()
        try:
            for row in conn.execute(
                "SELECT action, symbol FROM universe_change_log WHERE ts >= ? AND action IN ('APPLY_ADD', 'APPLY_REMOVE') ORDER BY ts DESC",
                (since,),
            ).fetchall():
                d = _row_to_dict(row)
                if d.get("action") == "APPLY_ADD" and d.get("symbol"):
                    added.append(d["symbol"])
                elif d.get("action") == "APPLY_REMOVE" and d.get("symbol"):
                    removed.append(d["symbol"])
        finally:
            conn.close()
    return added, removed
