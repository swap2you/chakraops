# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R42: Canonical Today ticket-queue + done-today persistence (SQLite under data/)."""

from __future__ import annotations

import json
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


def _db_path() -> Path:
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "ticket_queue_r42.db"
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "ticket_queue_r42.db"


def set_ticket_queue_db_path(path: Path) -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_ticket_queue_db_path() -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_ticket_queue_db() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS ticket_queue (
        id TEXT PRIMARY KEY,
        ticket_id TEXT,
        symbol TEXT NOT NULL,
        strategy TEXT NOT NULL,
        action TEXT NOT NULL,
        created_ts TEXT NOT NULL,
        journal_saved INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS done_today (
        symbol TEXT NOT NULL,
        day TEXT NOT NULL,
        created_ts TEXT NOT NULL,
        PRIMARY KEY (symbol, day)
    );
    """
    with _LOCK:
        c = _conn()
        try:
            c.executescript(sql)
            c.commit()
        finally:
            c.close()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_queue(*, include_archived: bool = False) -> List[Dict[str, Any]]:
    init_ticket_queue_db()
    with _LOCK:
        c = _conn()
        try:
            if include_archived:
                rows = c.execute(
                    "SELECT * FROM ticket_queue ORDER BY created_ts DESC"
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM ticket_queue WHERE archived=0 ORDER BY created_ts DESC"
                ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r["id"],
                        "ticket_id": r["ticket_id"] or r["id"],
                        "symbol": r["symbol"],
                        "strategy": r["strategy"],
                        "action": r["action"],
                        "created_ts": r["created_ts"],
                        "journal_saved": bool(r["journal_saved"]),
                        "archived": bool(r["archived"]),
                    }
                )
            return out
        finally:
            c.close()


def replace_queue(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Full replace of active queue (archived preserved)."""
    init_ticket_queue_db()
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM ticket_queue WHERE archived=0")
            for raw in items:
                iid = str(raw.get("id") or uuid.uuid4())
                c.execute(
                    """
                    INSERT INTO ticket_queue
                    (id, ticket_id, symbol, strategy, action, created_ts, journal_saved, archived)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        iid,
                        str(raw.get("ticket_id") or iid),
                        str(raw.get("symbol") or "").strip().upper(),
                        str(raw.get("strategy") or "CSP").strip().upper(),
                        str(raw.get("action") or "OPEN").strip().upper(),
                        str(raw.get("created_ts") or _now()),
                        1 if raw.get("journal_saved") else 0,
                    ),
                )
            c.commit()
        finally:
            c.close()
    return list_queue()


def add_queue_item(item: Dict[str, Any]) -> Dict[str, Any]:
    init_ticket_queue_db()
    iid = str(item.get("id") or uuid.uuid4())
    row = {
        "id": iid,
        "ticket_id": str(item.get("ticket_id") or iid),
        "symbol": str(item.get("symbol") or "").strip().upper(),
        "strategy": str(item.get("strategy") or "CSP").strip().upper(),
        "action": str(item.get("action") or "OPEN").strip().upper(),
        "created_ts": str(item.get("created_ts") or _now()),
        "journal_saved": bool(item.get("journal_saved")),
    }
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                """
                INSERT INTO ticket_queue
                (id, ticket_id, symbol, strategy, action, created_ts, journal_saved, archived)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    row["id"],
                    row["ticket_id"],
                    row["symbol"],
                    row["strategy"],
                    row["action"],
                    row["created_ts"],
                    1 if row["journal_saved"] else 0,
                ),
            )
            c.commit()
        finally:
            c.close()
    return row


def remove_queue_item(item_id: str) -> bool:
    init_ticket_queue_db()
    with _LOCK:
        c = _conn()
        try:
            cur = c.execute("UPDATE ticket_queue SET archived=1 WHERE id=? OR ticket_id=?", (item_id, item_id))
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()


def list_done_today(day: str) -> List[Dict[str, str]]:
    init_ticket_queue_db()
    with _LOCK:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT symbol, day FROM done_today WHERE day=? ORDER BY symbol",
                (day,),
            ).fetchall()
            return [{"symbol": r["symbol"], "date": r["day"]} for r in rows]
        finally:
            c.close()


def mark_done_today(symbol: str, day: str) -> Dict[str, str]:
    init_ticket_queue_db()
    sym = (symbol or "").strip().upper()
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                """
                INSERT OR REPLACE INTO done_today (symbol, day, created_ts)
                VALUES (?, ?, ?)
                """,
                (sym, day, _now()),
            )
            c.commit()
        finally:
            c.close()
    return {"symbol": sym, "date": day}


def migrate_from_payload(queue: List[Dict[str, Any]], done: List[Dict[str, str]], day: str) -> Dict[str, Any]:
    """One-shot import from browser localStorage payload."""
    q = replace_queue(queue or [])
    done_out = []
    for d in done or []:
        sym = (d.get("symbol") or "").strip().upper()
        dday = (d.get("date") or day or "").strip()
        if sym and dday:
            done_out.append(mark_done_today(sym, dday))
    return {"queue": q, "done_today": list_done_today(day), "migrated": True}
