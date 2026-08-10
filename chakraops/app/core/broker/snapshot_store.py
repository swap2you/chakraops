# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R52 last-good broker snapshot store (SQLite + JSON under data/).

Fail-closed: never replace a good snapshot with zeros / empty wipe on failure.
On sync failure, keep last-good and mark stale.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.broker.models import BrokerSnapshot, utc_now_iso

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_DIR: Optional[Path] = None


def set_snapshot_store_dir(path: Path) -> None:
    global _OVERRIDE_DIR
    _OVERRIDE_DIR = Path(path).resolve()
    _OVERRIDE_DIR.mkdir(parents=True, exist_ok=True)


def reset_snapshot_store_dir() -> None:
    global _OVERRIDE_DIR
    _OVERRIDE_DIR = None


def _store_dir() -> Path:
    if _OVERRIDE_DIR is not None:
        d = _OVERRIDE_DIR
        d.mkdir(parents=True, exist_ok=True)
        return d
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        base = Path(data_dir_env).resolve()
    else:
        base = Path(__file__).resolve().parents[3] / "data"
    d = base / "broker_snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _db_path() -> Path:
    return _store_dir() / "broker_snapshots_r52.db"


def _json_path(account_alias: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in account_alias)
    return _store_dir() / f"snapshot_{safe}.json"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_snapshot_store() -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS broker_snapshots (
        account_alias TEXT PRIMARY KEY,
        fetched_at TEXT NOT NULL,
        stale INTEGER NOT NULL DEFAULT 0,
        payload_json TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """
    with _LOCK:
        c = _conn()
        try:
            c.executescript(sql)
            c.commit()
        finally:
            c.close()


def load_snapshot(account_alias: str) -> Optional[BrokerSnapshot]:
    init_snapshot_store()
    alias = (account_alias or "").strip()
    with _LOCK:
        c = _conn()
        try:
            row = c.execute(
                "SELECT payload_json FROM broker_snapshots WHERE account_alias=?",
                (alias,),
            ).fetchone()
            if row:
                return BrokerSnapshot.from_dict(json.loads(row["payload_json"]))
        finally:
            c.close()
    # JSON fallback
    path = _json_path(alias)
    if path.is_file():
        try:
            return BrokerSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_snapshot(snapshot: BrokerSnapshot, *, allow_zero_wipe: bool = False) -> Dict[str, Any]:
    """Persist snapshot. Rejects suspicious all-zero wipe over a prior non-zero good snapshot."""
    init_snapshot_store()
    alias = snapshot.account_alias
    existing = load_snapshot(alias)

    if existing and not allow_zero_wipe and _is_zero_wipe(snapshot) and not _is_zero_wipe(existing):
        logger.warning(
            "Refusing to replace last-good snapshot with zeros alias=%s",
            alias,
        )
        marked = BrokerSnapshot.from_dict(existing.to_dict())
        marked.stale = True
        marked.freshness = "stale"
        if "zero_wipe_rejected" not in marked.errors:
            marked.errors = list(marked.errors) + ["zero_wipe_rejected"]
        _write(marked)
        return {
            "saved": False,
            "reason": "zero_wipe_rejected",
            "stale": True,
            "account_alias": alias,
        }

    if snapshot.errors and existing and _is_empty_failure(snapshot) and not _is_empty_failure(existing):
        # Failure payload: keep last good, mark stale.
        marked = BrokerSnapshot.from_dict(existing.to_dict())
        marked.stale = True
        marked.freshness = "stale"
        for err in snapshot.errors:
            if err not in marked.errors:
                marked.errors = list(marked.errors) + [err]
        _write(marked)
        return {
            "saved": False,
            "reason": "sync_failure_kept_last_good",
            "stale": True,
            "account_alias": alias,
        }

    _write(snapshot)
    return {"saved": True, "stale": bool(snapshot.stale), "account_alias": alias}


def mark_stale(account_alias: str, *, error: Optional[str] = None) -> Optional[BrokerSnapshot]:
    snap = load_snapshot(account_alias)
    if not snap:
        return None
    snap.stale = True
    snap.freshness = "stale"
    if error and error not in snap.errors:
        snap.errors = list(snap.errors) + [error]
    _write(snap)
    return snap


def persist_sync_result(account_alias: str, snapshot: Optional[BrokerSnapshot], *, failed: bool = False) -> Dict[str, Any]:
    """High-level helper used by API/provider: on failure keep last-good and mark stale."""
    if failed or snapshot is None:
        existing = mark_stale(account_alias, error="sync_failed")
        return {
            "saved": False,
            "reason": "sync_failed",
            "stale": True,
            "has_last_good": existing is not None,
            "account_alias": account_alias,
            "snapshot": existing.masked_for_api() if existing else None,
        }
    return save_snapshot(snapshot)


def _write(snapshot: BrokerSnapshot) -> None:
    init_snapshot_store()
    payload = snapshot.to_dict()
    # Ensure no full account numbers in persisted JSON.
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    now = utc_now_iso()
    with _LOCK:
        c = _conn()
        try:
            c.execute(
                """
                INSERT INTO broker_snapshots (account_alias, fetched_at, stale, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_alias) DO UPDATE SET
                    fetched_at=excluded.fetched_at,
                    stale=excluded.stale,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    snapshot.account_alias,
                    snapshot.fetched_at or now,
                    1 if snapshot.stale else 0,
                    blob,
                    now,
                ),
            )
            c.commit()
        finally:
            c.close()
        try:
            _json_path(snapshot.account_alias).write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("JSON snapshot write failed: %s", type(exc).__name__)


def _is_zero_wipe(snapshot: BrokerSnapshot) -> bool:
    if not snapshot.balances.looks_like_zero_wipe():
        return False
    return not snapshot.equity_positions and not snapshot.option_positions


def _is_empty_failure(snapshot: BrokerSnapshot) -> bool:
    if not snapshot.errors:
        return False
    empty_bal = (
        snapshot.balances.cash is None
        and snapshot.balances.buying_power is None
        and snapshot.balances.equity is None
        and snapshot.balances.market_value is None
    )
    return empty_bal and not snapshot.equity_positions and not snapshot.option_positions
