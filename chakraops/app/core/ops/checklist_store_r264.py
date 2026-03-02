# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.4: Checklist persistence (EOD / Weekly) — SQLite under data/. Code-only; no FAIL_/WARN_."""

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

KIND_EOD = "EOD"
KIND_WEEKLY = "WEEKLY"
STATUS_OPEN = "OPEN"
STATUS_DONE = "DONE"


def _checklist_db_path() -> Path:
    """Checklist DB under data/ (not out/)."""
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "checklist_r264.db"


def set_checklist_db_path(path: Path) -> None:
    """Override DB path (for tests)."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_checklist_db_path() -> None:
    """Reset to default path."""
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _get_conn() -> sqlite3.Connection:
    path = _checklist_db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_checklist_db() -> None:
    """Create checklist_state table if not exist. Safe to call repeatedly."""
    sql = """
    CREATE TABLE IF NOT EXISTS checklist_state (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        done_ts TEXT,
        notes TEXT,
        created_ts TEXT NOT NULL,
        UNIQUE(kind, key)
    );
    CREATE INDEX IF NOT EXISTS idx_checklist_kind_key ON checklist_state(kind, key);
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


def checklist_get(kind: str, key: str) -> Optional[Dict[str, Any]]:
    """Get one checklist row by kind and key."""
    init_checklist_db()
    kind = (kind or "").strip().upper()
    key = (key or "").strip()
    if kind not in (KIND_EOD, KIND_WEEKLY) or not key:
        return None
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM checklist_state WHERE kind = ? AND key = ?",
                (kind, key),
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def checklist_set_done(
    kind: str,
    key: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Set status to DONE for kind+key. Upserts row. Returns record."""
    init_checklist_db()
    kind = (kind or "").strip().upper()
    key = (key or "").strip()
    if kind not in (KIND_EOD, KIND_WEEKLY) or not key:
        raise ValueError("kind must be EOD or WEEKLY and key non-empty")
    now = _now_iso()
    notes_val = (notes or "").strip()[:2000] or None
    existing = checklist_get(kind, key)
    with _LOCK:
        conn = _get_conn()
        try:
            if existing:
                conn.execute(
                    "UPDATE checklist_state SET status = ?, done_ts = ?, notes = COALESCE(?, notes) WHERE kind = ? AND key = ?",
                    (STATUS_DONE, now, notes_val, kind, key),
                )
            else:
                conn.execute(
                    "INSERT INTO checklist_state (id, kind, key, status, done_ts, notes, created_ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), kind, key, STATUS_DONE, now, notes_val, now),
                )
            conn.commit()
        finally:
            conn.close()
    return checklist_get(kind, key) or {}


def checklist_ensure_open(kind: str, key: str) -> Dict[str, Any]:
    """Ensure a row exists with status OPEN for kind+key. Creates if missing. Returns record."""
    init_checklist_db()
    kind = (kind or "").strip().upper()
    key = (key or "").strip()
    if kind not in (KIND_EOD, KIND_WEEKLY) or not key:
        raise ValueError("kind must be EOD or WEEKLY and key non-empty")
    existing = checklist_get(kind, key)
    if existing:
        return existing
    now = _now_iso()
    row_id = str(uuid.uuid4())
    with _LOCK:
        conn = _get_conn()
        try:
            try:
                conn.execute(
                    "INSERT INTO checklist_state (id, kind, key, status, done_ts, notes, created_ts) VALUES (?, ?, ?, ?, NULL, NULL, ?)",
                    (row_id, kind, key, STATUS_OPEN, now),
                )
            except sqlite3.IntegrityError:
                pass
            conn.commit()
        finally:
            conn.close()
    return checklist_get(kind, key) or {"kind": kind, "key": key, "status": STATUS_OPEN}


def checklist_list(
    kind: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List checklist rows. Optional filter by kind and status."""
    init_checklist_db()
    conditions: List[str] = []
    params: List[Any] = []
    if kind:
        conditions.append("kind = ?")
        params.append((kind or "").strip().upper())
    if status:
        conditions.append("status = ?")
        params.append((status or "").strip().upper())
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                f"SELECT * FROM checklist_state{where} ORDER BY key DESC LIMIT ?",
                params,
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()
