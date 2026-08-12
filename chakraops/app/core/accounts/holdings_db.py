# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.1: SQLite persistence for account profile, balances, holdings (manual entry), and R23.0 share_positions."""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
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
    CREATE TABLE IF NOT EXISTS share_positions (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        avg_cost REAL,
        opened_at TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        target_price REAL,
        stop_price REAL,
        UNIQUE(account_id, symbol),
        FOREIGN KEY (account_id) REFERENCES account_profile(id)
    );
    CREATE TABLE IF NOT EXISTS share_positions_closed (
        id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        avg_cost REAL,
        opened_at TEXT,
        closed_at TEXT NOT NULL,
        exit_price REAL NOT NULL,
        realized_pnl REAL,
        close_notes TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (account_id) REFERENCES account_profile(id)
    );
    """
    with _LOCK:
        conn = _get_conn()
        try:
            conn.executescript(sql)
            conn.commit()
            # R25.2: Migrate existing DBs — add target_price, stop_price if missing
            for col in ("target_price", "stop_price"):
                try:
                    conn.execute(f"ALTER TABLE share_positions ADD COLUMN {col} REAL")
                    conn.commit()
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise
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


def get_account_summary(account_id: str | None = None) -> Dict[str, Any]:
    """Return summary for account: profile, balances, holdings count, updated_at.

    ``account_id`` defaults to the default account when omitted/empty.
    """
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT p.id, p.name, p.broker, p.base_currency, p.updated_at AS profile_updated, b.cash, b.buying_power, b.updated_at AS balances_updated FROM account_profile p LEFT JOIN account_balances b ON p.id = b.account_id WHERE p.id = ?",
                (aid,),
            ).fetchone()
            if not row:
                empty = _empty_summary()
                empty["account_id"] = aid
                return empty
            count = conn.execute(
                "SELECT COUNT(*) FROM holdings WHERE account_id = ?", (aid,)
            ).fetchone()[0]
            # Preserve explicit zero cash; do not coerce missing LEFT JOIN balances to pretend present.
            cash_raw = row["cash"]
            bp_raw = row["buying_power"]
            has_balance_row = row["balances_updated"] is not None or cash_raw is not None or bp_raw is not None
            return {
                "account_id": row["id"],
                "name": row["name"],
                "broker": row["broker"],
                "base_currency": row["base_currency"],
                "cash": float(cash_raw) if cash_raw is not None else (0.0 if has_balance_row else None),
                "buying_power": float(bp_raw) if bp_raw is not None else (0.0 if has_balance_row else None),
                "balances_present": bool(has_balance_row),
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
        "balances_present": False,
        "holdings_count": 0,
        "profile_updated_at": now,
        "balances_updated_at": now,
    }


# ---------------------------------------------------------------------------
# Balances
# ---------------------------------------------------------------------------


def set_balances(cash: float, buying_power: float, account_id: str | None = None) -> Dict[str, Any]:
    """Set cash and buying_power for account (default account when omitted). Returns updated summary."""
    init_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    with _LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO account_balances (account_id, cash, buying_power, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET cash = ?, buying_power = ?, updated_at = ?",
                (aid, cash, buying_power, now, cash, buying_power, now),
            )
            conn.commit()
        finally:
            conn.close()
    return get_account_summary(aid)


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
    Return symbol -> total shares for default account.
    When broker capital is FRESH, use broker equity quantities for live CC gating.
    Manual holdings alone never create live CC eligibility while broker is fresh.
    """
    try:
        from app.core.portfolio.capital_authority_r70 import STATE_FRESH, broker_share_quantities, get_capital_snapshot

        cap = get_capital_snapshot("acct_individual", allow_manual_fallback=False)
        if cap.get("state") == STATE_FRESH:
            return {k: v for k, v in broker_share_quantities("acct_individual").items() if v >= 1}
    except Exception:
        pass
    return get_total_shares_for_evaluation(_DEFAULT_ACCOUNT_ID)


def get_total_shares_for_evaluation(account_id: str) -> Dict[str, int]:
    """
    R23.0: Return symbol -> total shares for account (holdings + share_positions).
    Used for CC eligibility: total_shares >= 100.
    """
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    with _LOCK:
        conn = _get_conn()
        try:
            # Holdings: symbol -> shares
            rows = conn.execute(
                "SELECT symbol, shares FROM holdings WHERE account_id = ? AND shares >= 1",
                (aid,),
            ).fetchall()
            total: Dict[str, int] = {r["symbol"]: int(r["shares"]) for r in rows}
            # Add share_positions (same symbol => add quantity)
            rows2 = conn.execute(
                "SELECT symbol, quantity FROM share_positions WHERE account_id = ? AND quantity >= 1",
                (aid,),
            ).fetchall()
            for r in rows2:
                sym = r["symbol"]
                total[sym] = total.get(sym, 0) + int(r["quantity"])
            return {k: v for k, v in total.items() if v >= 1}
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Share positions (R23.0). R27.7: Cost basis = avg_cost * quantity (stored);
# unrealized P/L computed at request time from mark; opened_at used for days_held.
# ---------------------------------------------------------------------------


def list_share_positions(account_id: str) -> List[Dict[str, Any]]:
    """List all share positions for account. Symbol normalized to uppercase in response."""
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, account_id, symbol, quantity, avg_cost, opened_at, notes, created_at, updated_at, target_price, stop_price
                   FROM share_positions WHERE account_id = ? ORDER BY symbol""",
                (aid,),
            ).fetchall()
            return [_row_to_share_position(r) for r in rows]
        finally:
            conn.close()


def get_share_position(account_id: str, symbol: str) -> Optional[Dict[str, Any]]:
    """Get share position for account+symbol. Returns None if not found."""
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    sym = (symbol or "").strip().upper()
    if not sym:
        return None
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                """SELECT id, account_id, symbol, quantity, avg_cost, opened_at, notes, created_at, updated_at, target_price, stop_price
                   FROM share_positions WHERE account_id = ? AND symbol = ?""",
                (aid, sym),
            ).fetchone()
            return _row_to_share_position(row) if row else None
        finally:
            conn.close()


def _row_to_share_position(r: Any) -> Dict[str, Any]:
    if r is None:
        return {}
    out = {
        "id": r["id"],
        "account_id": r["account_id"],
        "symbol": r["symbol"],
        "quantity": int(r["quantity"]),
        "avg_cost": float(r["avg_cost"]) if r["avg_cost"] is not None else None,
        "opened_at": r["opened_at"],
        "notes": r["notes"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }
    # R25.2: target/stop (sqlite3.Row has no .get; use try/except for compat)
    try:
        tp = r["target_price"]
        out["target_price"] = float(tp) if tp is not None else None
    except (KeyError, TypeError, ValueError):
        out["target_price"] = None
    try:
        sp = r["stop_price"]
        out["stop_price"] = float(sp) if sp is not None else None
    except (KeyError, TypeError, ValueError):
        out["stop_price"] = None
    return out


def upsert_share_position(
    account_id: str,
    symbol: str,
    quantity: int,
    avg_cost: Optional[float] = None,
    opened_at: Optional[str] = None,
    notes: Optional[str] = None,
    target_price: Optional[float] = None,
    stop_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Upsert share position. One row per (account_id, symbol). Returns the position row. R25.2: target_price, stop_price optional."""
    init_db()
    from datetime import datetime, timezone
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    if not isinstance(quantity, int) or quantity < 0:
        raise ValueError("quantity must be a non-negative integer")
    if avg_cost is not None and (not isinstance(avg_cost, (int, float)) or avg_cost < 0):
        raise ValueError("avg_cost must be non-negative if provided")
    # R25.2: soft validation — stop < entry, target > entry when entry (avg_cost) exists; never hard fail with raw codes
    entry = float(avg_cost) if avg_cost is not None else None
    if stop_price is not None:
        try:
            stop_f = float(stop_price)
            if entry is not None and stop_f >= entry:
                stop_price = None  # ignore invalid stop (above entry)
        except (TypeError, ValueError):
            stop_price = None
    if target_price is not None:
        try:
            tgt_f = float(target_price)
            if entry is not None and tgt_f <= entry:
                target_price = None  # ignore invalid target (below entry)
        except (TypeError, ValueError):
            target_price = None
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _get_conn()
        try:
            existing = conn.execute(
                "SELECT id FROM share_positions WHERE account_id = ? AND symbol = ?",
                (aid, sym),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE share_positions SET quantity = ?, avg_cost = ?, opened_at = ?, notes = ?, updated_at = ?, target_price = ?, stop_price = ?
                       WHERE account_id = ? AND symbol = ?""",
                    (quantity, avg_cost, opened_at, notes, now, target_price, stop_price, aid, sym),
                )
                conn.commit()
            else:
                pos_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO share_positions (id, account_id, symbol, quantity, avg_cost, opened_at, notes, created_at, updated_at, target_price, stop_price)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pos_id, aid, sym, quantity, avg_cost, opened_at, notes, now, now, target_price, stop_price),
                )
                conn.commit()
            row = conn.execute(
                """SELECT id, account_id, symbol, quantity, avg_cost, opened_at, notes, created_at, updated_at, target_price, stop_price
                   FROM share_positions WHERE account_id = ? AND symbol = ?""",
                (aid, sym),
            ).fetchone()
            return _row_to_share_position(row)
        finally:
            conn.close()


def delete_share_position(account_id: str, symbol: str) -> bool:
    """Remove share position for account+symbol. Returns True if deleted."""
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    with _LOCK:
        conn = _get_conn()
        try:
            cur = conn.execute(
                "DELETE FROM share_positions WHERE account_id = ? AND symbol = ?",
                (aid, sym),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Share positions closed (R23.5.0)
# ---------------------------------------------------------------------------


def close_share_position(
    account_id: str,
    symbol: str,
    exit_price: float,
    exit_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Close share position: copy to share_positions_closed with realized_pnl, then delete.
    exit_date: ISO datetime string; default now UTC.
    Returns closed record with realized_pnl.
    """
    init_db()
    from datetime import datetime, timezone
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("symbol is required")
    if not isinstance(exit_price, (int, float)):
        raise ValueError("exit_price is required and must be a number")
    exit_price_f = float(exit_price)
    closed_at = exit_date if exit_date else datetime.now(timezone.utc).isoformat()
    with _LOCK:
        conn = _get_conn()
        try:
            row = conn.execute(
                """SELECT id, account_id, symbol, quantity, avg_cost, opened_at, notes, created_at, updated_at
                   FROM share_positions WHERE account_id = ? AND symbol = ?""",
                (aid, sym),
            ).fetchone()
            if not row:
                raise ValueError(f"No share position for {sym}")
            qty = int(row["quantity"])
            avg = float(row["avg_cost"]) if row["avg_cost"] is not None else None
            realized_pnl = ((exit_price_f - avg) * qty) if (avg is not None and qty > 0) else None
            closed_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO share_positions_closed
                   (id, account_id, symbol, quantity, avg_cost, opened_at, closed_at, exit_price, realized_pnl, close_notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    closed_id,
                    row["account_id"],
                    row["symbol"],
                    qty,
                    row["avg_cost"],
                    row["opened_at"],
                    closed_at,
                    exit_price_f,
                    realized_pnl,
                    notes,
                    row["created_at"],
                ),
            )
            conn.execute(
                "DELETE FROM share_positions WHERE account_id = ? AND symbol = ?",
                (aid, sym),
            )
            conn.commit()
            out = {
                "id": closed_id,
                "account_id": row["account_id"],
                "symbol": row["symbol"],
                "quantity": qty,
                "avg_cost": avg,
                "opened_at": row["opened_at"],
                "closed_at": closed_at,
                "exit_price": exit_price_f,
                "realized_pnl": realized_pnl,
                "close_notes": notes,
            }
            return out
        finally:
            conn.close()


def list_closed_share_positions(account_id: str) -> List[Dict[str, Any]]:
    """List closed share positions for account, newest first."""
    init_db()
    aid = (account_id or "").strip() or _DEFAULT_ACCOUNT_ID
    with _LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                """SELECT id, account_id, symbol, quantity, avg_cost, opened_at, closed_at, exit_price, realized_pnl, close_notes, created_at
                   FROM share_positions_closed WHERE account_id = ? ORDER BY closed_at DESC""",
                (aid,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "account_id": r["account_id"],
                    "symbol": r["symbol"],
                    "quantity": int(r["quantity"]),
                    "avg_cost": float(r["avg_cost"]) if r["avg_cost"] is not None else None,
                    "opened_at": r["opened_at"],
                    "closed_at": r["closed_at"],
                    "exit_price": float(r["exit_price"]),
                    "realized_pnl": float(r["realized_pnl"]) if r["realized_pnl"] is not None else None,
                    "close_notes": r["close_notes"],
                }
                for r in rows
            ]
        finally:
            conn.close()
