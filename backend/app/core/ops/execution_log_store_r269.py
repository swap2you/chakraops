# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.9: Ops execution log — record overrides and done transitions. SQLite under DATA_DIR. Code-only; no FAIL_/WARN_."""

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

EVENT_MARK_DONE = "MARK_DONE"
EVENT_SKIP_JOURNAL = "SKIP_JOURNAL"
EVENT_EOD_OVERRIDE = "EOD_OVERRIDE"
VALID_EVENTS = (EVENT_MARK_DONE, EVENT_SKIP_JOURNAL, EVENT_EOD_OVERRIDE)
REASON_MAX_LEN = 140


def _execution_log_db_path() -> Path:
    """Execution log DB under data/. R26.7: DATA_DIR env override."""
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "execution_log_r269.db"
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "execution_log_r269.db"


def set_execution_log_db_path(path: Path) -> None:
    """Override DB path (for tests)."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_execution_log_db_path() -> None:
    """Reset to default path."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _get_conn() -> sqlite3.Connection:
    path = _execution_log_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_execution_log_db() -> None:
    """Create execution_log table if not exist. Safe to call repeatedly."""
    sql = """
    CREATE TABLE IF NOT EXISTS execution_log (
        id TEXT PRIMARY KEY,
        ts TEXT NOT NULL,
        symbol TEXT,
        strategy TEXT,
        action TEXT,
        ticket_id TEXT,
        event_type TEXT NOT NULL,
        reason TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_execution_log_ts ON execution_log(ts);
    CREATE INDEX IF NOT EXISTS idx_execution_log_event_type ON execution_log(event_type);
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


def execution_log_append(
    event_type: str,
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    action: Optional[str] = None,
    ticket_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one execution log event. reason truncated to REASON_MAX_LEN. Returns record."""
    init_execution_log_db()
    event_type = (event_type or "").strip().upper()
    if event_type not in VALID_EVENTS:
        raise ValueError(f"event_type must be one of {VALID_EVENTS}")
    reason_val = (reason or "").strip()[:REASON_MAX_LEN] or None
    now = _now_iso()
    row_id = str(uuid.uuid4())
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                """INSERT INTO execution_log (id, ts, symbol, strategy, action, ticket_id, event_type, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (row_id, now, (symbol or "").strip() or None, (strategy or "").strip() or None,
                 (action or "").strip() or None, (ticket_id or "").strip() or None, event_type, reason_val),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "id": row_id,
        "ts": now,
        "symbol": (symbol or "").strip() or None,
        "strategy": (strategy or "").strip() or None,
        "action": (action or "").strip() or None,
        "ticket_id": (ticket_id or "").strip() or None,
        "event_type": event_type,
        "reason": reason_val,
    }


def execution_log_list(
    date: Optional[str] = None,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """List execution log rows. If date=YYYY-MM-DD, filter by ts date (UTC date). Order ts desc."""
    init_execution_log_db()
    conditions: List[str] = []
    params: List[Any] = []
    if date and len(date) >= 10:
        date_prefix = date[:10]
        conditions.append("ts LIKE ?")
        params.append(f"{date_prefix}%")
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM execution_log{where} ORDER BY ts DESC LIMIT ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
