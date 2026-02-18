# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.1: SQLite persistence for account profile, balances, and holdings (manual entry)."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_DEFAULT_ACCOUNT_ID = "default"


def _db_path() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "account.db"


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist. Safe to call repeatedly."""
    sql = """
    CREATE TABLE IF NOT EXISTS account_profile (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL DEFAULT 'Default',
        broker TEXT,
        base_currency TEXT NOT NULL DEFAULT 'USD',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS account_balances (
        account_id TEXT NOT NULL PRIMARY KEY,
        cash REAL NOT NULL DEFAULT 0,
        buying_power REAL NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES account_profile(id)
    );
    CREATE TABLE IF NOT EXISTS holdings (
        account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        shares INTEGER NOT NULL DEFAULT 0,
        avg_cost REAL,
        source TEXT NOT NULL DEFAULT 'manual',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (account_id, symbol),
        FOREIGN KEY (account_id) REFERENCES account_profile(id)
    );
    """
    with _LOCK:
        conn = _get_conn()
        try:
            conn.executescript(sql)
            conn.commit()
            # Ensure default profile exists
            cur = conn.execute(
                "SELECT 1 FROM account_profile WHERE id = ?", (_DEFAULT_ACCOUNT_ID,)
            )
            if cur.fetchone() is None:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "INSERT INTO account_profile (id, name, broker, base_currency, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (_DEFAULT_ACCOUNT_ID, "Default", None, "USD", now, now),
                )
                conn.execute(
                    "INSERT INTO account_balances (account_id, cash, buying_power, updated_at) VALUES (?, 0, 0, ?)",
                    (_DEFAULT_ACCOUNT_ID, now),
                )
                conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Account summary (profile + balances)
# ---------------------------------------------------------------------------


def get_account_summary() -> Dict[str, Any]:
    """Return summary for default account: profile, balances, holdings count, updated_at."""
    init_db()
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT p.id, p.name, p.broker, p.base_currency, p.updated_at AS profile_updated, b.cash, b.buying_power, b.updated_at AS balances_updated FROM account_profile p LEFT JOIN account_balances b ON p.id = b.account_id WHERE p.id = ?",
                (_DEFAULT_ACCOUNT_ID,),
            ).fetchone()
            if not row:
                return _empty_summary()
            count = conn.execute(
                "SELECT COUNT(*) FROM holdings WHERE account_id = ?", (_DEFAULT_ACCOUNT_ID,)
            ).fetchone()[0]
            return {
                "account_id": row["id"],
                "name": row["name"],
                "broker": row["broker"],
                "base_currency": row["base_currency"],
                "cash": float(row["cash"] or 0),
                "buying_power": float(row["buying_power"] or 0),
                "holdings_count": count,
                "profile_updated_at": row["profile_updated"],
                "balances_updated_at": row["balances_updated"],
            }
        finally:
            conn.close()


def _empty_summary() -> Dict[str, Any]:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return {
        "account_id": _DEFAULT_ACCOUNT_ID,
        "name": "Default",
        "broker": None,
        "base_currency": "USD",
        "cash": 0.0,
        "buying_power": 0.0,
        "holdings_count": 0,
        "profile_updated_at": now,
        "balances_updated_at": now,
    }


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------


def set_balances(cash: float, buying_power: float) -> Dict[str, Any]:
    """Set cash and buying_power for default account. Returns updated summary."""
    init_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO account_balances (account_id, cash, buying_power, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET cash = ?, buying_power = ?, updated_at = ?",
                (_DEFAULT_ACCOUNT_ID, cash, buying_power, now, cash, buying_power, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_account_summary()


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------


def list_holdings() -> List[Dict[str, Any]]:
    """List all holdings for default account."""
    init_db()
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT symbol, shares, avg_cost, source, updated_at FROM holdings WHERE account_id = ? ORDER BY symbol",
                (_DEFAULT_ACCOUNT_ID,),
            ).fetchall()
            return [
                {
                    "symbol": r["symbol"],
                    "shares": int(r["shares"]),
                    "avg_cost": float(r["avg_cost"]) if r["avg_cost"] is not None else None,
                    "source": r["source"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()


def upsert_holding(symbol: str, shares: int, avg_cost: Optional[float] = None) -> Dict[str, Any]:
    """Add or update holding. symbol normalized to uppercase. Returns the holding row."""
    init_db()
    from datetime import datetime, timezone
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    if not isinstance(shares, int) or shares < 0:
        raise ValueError("shares must be a non-negative integer")
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO holdings (account_id, symbol, shares, avg_cost, source, updated_at) VALUES (?, ?, ?, ?, 'manual', ?) ON CONFLICT(account_id, symbol) DO UPDATE SET shares = ?, avg_cost = ?, updated_at = ?",
                (_DEFAULT_ACCOUNT_ID, sym, shares, avg_cost, now, shares, avg_cost, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT symbol, shares, avg_cost, source, updated_at FROM holdings WHERE account_id = ? AND symbol = ?",
                (_DEFAULT_ACCOUNT_ID, sym),
            ).fetchone()
            return {
                "symbol": row["symbol"],
                "shares": int(row["shares"]),
                "avg_cost": float(row["avg_cost"]) if row["avg_cost"] is not None else None,
                "source": row["source"],
                "updated_at": row["updated_at"],
            }
        finally:
            conn.close()


def delete_holding(symbol: str) -> bool:
    """Remove holding for symbol. Returns True if deleted, False if not found."""
    init_db()
    sym = (symbol or "").strip().upper()
    with _LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM holdings WHERE account_id = ? AND symbol = ?",
                (_DEFAULT_ACCOUNT_ID, sym),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def get_holdings_for_evaluation() -> Dict[str, int]:
    """
    Return symbol -> shares for default account. Used by eligibility engine for CC gating.
    Only includes holdings with shares >= 1 (no zero entries).
    """
    init_db()
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT symbol, shares FROM holdings WHERE account_id = ? AND shares >= 1",
                (_DEFAULT_ACCOUNT_ID,),
            ).fetchall()
            return {r["symbol"]: int(r["shares"]) for r in rows}
        finally:
            conn.close()
