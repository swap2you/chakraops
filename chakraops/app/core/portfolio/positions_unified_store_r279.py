# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.9: Unified positions store — read-only aggregation from live shares, live options, paper. Safe labels only."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_OVERRIDE_PATH: Optional[Path] = None

INSTRUMENT_SHARES = "SHARES"
INSTRUMENT_CSP = "CSP"
INSTRUMENT_CC = "CC"

# Prohibited in API responses (non-negotiable)
_FAIL_WARN_PATTERN = re.compile(r"FAIL_|WARN_", re.I)


def _positions_db_path() -> Path:
    if _OVERRIDE_PATH is not None:
        return _OVERRIDE_PATH
    data_dir_env = os.environ.get("DATA_DIR")
    if data_dir_env:
        data_dir = Path(data_dir_env).resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "positions.db"
    base = Path(__file__).resolve().parents[3]
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "positions.db"


def get_positions_db_path() -> Path:
    return _positions_db_path()


def set_positions_db_path(path: Path) -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = Path(path).resolve()


def reset_positions_db_path() -> None:
    global _OVERRIDE_PATH
    _OVERRIDE_PATH = None


def _safe_str(val: Any) -> str:
    """Return string with no FAIL_/WARN_ substrings (safe label)."""
    if val is None:
        return ""
    s = str(val).strip()
    if _FAIL_WARN_PATTERN.search(s):
        return ""  # or a generic safe placeholder; requirement: never expose raw
    return s


def _fees_from_position(p: Any) -> Optional[float]:
    """Sum open_fees + close_fees for a position object; return None if both 0."""
    o = float(getattr(p, "open_fees", 0) or 0)
    c = float(getattr(p, "close_fees", 0) or 0)
    return (o + c) or None


def _safe_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow sanitize dict values so no value contains FAIL_/WARN_."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str) and _FAIL_WARN_PATTERN.search(v):
            out[k] = ""
        elif isinstance(v, dict):
            out[k] = _safe_dict(v)
        elif isinstance(v, list):
            out[k] = [_safe_str(x) if isinstance(x, str) else x for x in v]
        else:
            out[k] = v
    return out


def init_db() -> None:
    """Create positions_open and positions_closed tables if they do not exist."""
    sql = """
    CREATE TABLE IF NOT EXISTS positions_open (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        instrument_type TEXT NOT NULL,
        is_paper INTEGER NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL,
        avg_price REAL,
        strike REAL,
        expiry TEXT,
        right TEXT,
        opened_ts TEXT NOT NULL,
        link_id TEXT,
        notes TEXT,
        tags TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_positions_open_symbol ON positions_open(symbol);
    CREATE INDEX IF NOT EXISTS idx_positions_open_instrument ON positions_open(instrument_type);
    CREATE INDEX IF NOT EXISTS idx_positions_open_opened ON positions_open(opened_ts);

    CREATE TABLE IF NOT EXISTS positions_closed (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        instrument_type TEXT NOT NULL,
        is_paper INTEGER NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL,
        avg_price REAL,
        strike REAL,
        expiry TEXT,
        right TEXT,
        opened_ts TEXT NOT NULL,
        link_id TEXT,
        notes TEXT,
        tags TEXT,
        closed_ts TEXT NOT NULL,
        realized_pl REAL,
        fees REAL
    );
    CREATE INDEX IF NOT EXISTS idx_positions_closed_symbol ON positions_closed(symbol);
    CREATE INDEX IF NOT EXISTS idx_positions_closed_closed ON positions_closed(closed_ts);
    """
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()


def _sort_key_open(row: Dict[str, Any]) -> tuple:
    """Stable sort: symbol, instrument_type, expiry, strike, opened_ts."""
    sym = (row.get("symbol") or "").strip().upper()
    itype = (row.get("instrument_type") or "").upper()
    expiry = (row.get("expiry") or "")[:10]
    strike = float(row.get("strike") or 0)
    opened = (row.get("opened_ts") or "")[:26]
    return (sym, itype, expiry, strike, opened)


def _sort_key_closed(row: Dict[str, Any]) -> tuple:
    """Stable sort for closed: symbol, type, expiry, strike, opened_ts, closed_ts."""
    base = _sort_key_open(row)
    closed = (row.get("closed_ts") or "")[:26]
    return base + (closed,)


def build_unified_positions(
    state: str = "open",
    include_paper: bool = True,
    instrument_type: Optional[str] = None,
    symbol: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Read-only aggregation: pull from holdings_db (live shares), positions store (live options), paper store.
    Returns list of unified rows with stable ids and deterministic ordering. No FAIL_/WARN_ in values.
    """
    init_db()  # Ensure schema exists (e.g. for tests that set_positions_db_path)
    want_open = (state or "open").strip().lower() != "closed"
    rows: List[Dict[str, Any]] = []

    # --- Live shares (holdings_db) ---
    try:
        from app.core.accounts.holdings_db import list_share_positions, list_closed_share_positions, _DEFAULT_ACCOUNT_ID
        if want_open:
            for sp in list_share_positions(_DEFAULT_ACCOUNT_ID):
                sid = (sp.get("id") or "").strip()
                if not sid:
                    continue
                sym = (sp.get("symbol") or "").strip().upper()
                if symbol and (symbol or "").strip().upper() != sym:
                    continue
                qty = int(sp.get("quantity") or 0)
                if qty <= 0:
                    continue
                rows.append({
                    "id": f"live_shares_{sid}",
                    "symbol": sym,
                    "instrument_type": INSTRUMENT_SHARES,
                    "is_paper": 0,
                    "qty": qty,
                    "avg_price": float(sp["avg_cost"]) if sp.get("avg_cost") is not None else None,
                    "strike": None,
                    "expiry": None,
                    "right": None,
                    "opened_ts": (sp.get("opened_at") or sp.get("created_at") or ""),
                    "link_id": sid,
                    "notes": _safe_str(sp.get("notes")),
                    "tags": None,
                })
        else:
            for sp in list_closed_share_positions(_DEFAULT_ACCOUNT_ID):
                sid = (sp.get("id") or "").strip()
                if not sid:
                    continue
                sym = (sp.get("symbol") or "").strip().upper()
                if symbol and (symbol or "").strip().upper() != sym:
                    continue
                qty = int(sp.get("quantity") or 0)
                rows.append({
                    "id": f"live_shares_closed_{sid}",
                    "symbol": sym,
                    "instrument_type": INSTRUMENT_SHARES,
                    "is_paper": 0,
                    "qty": qty,
                    "avg_price": float(sp["avg_cost"]) if sp.get("avg_cost") is not None else None,
                    "strike": None,
                    "expiry": None,
                    "right": None,
                    "opened_ts": (sp.get("opened_at") or ""),
                    "link_id": sid,
                    "notes": _safe_str(sp.get("close_notes")),
                    "tags": None,
                    "closed_ts": (sp.get("closed_at") or ""),
                    "realized_pl": sp.get("realized_pnl"),
                    "fees": None,
                })
    except Exception as e:
        logger.warning("[R27.9] holdings_db aggregation failed: %s", e)

    # --- Live options (tracked positions store) ---
    try:
        from app.core.positions.store import list_positions as list_tracked
        status_filter = "OPEN" if want_open else "CLOSED"
        for p in list_tracked(status=status_filter, symbol=symbol):
            pid = getattr(p, "position_id", None) or getattr(p, "id", None) or ""
            pid = (pid or "").strip()
            if not pid:
                continue
            sym = (getattr(p, "symbol", None) or "").strip().upper()
            strat = (getattr(p, "strategy", None) or "").strip().upper()
            if strat == "STOCK":
                continue  # shares handled above
            itype = INSTRUMENT_CSP if strat == "CSP" else (INSTRUMENT_CC if strat == "CC" else "OPTION")
            if instrument_type and (instrument_type or "").strip().upper() != itype:
                continue
            contracts = int(getattr(p, "contracts", 0) or 0)
            qty = contracts * 100 if contracts else (int(getattr(p, "quantity", 0) or 0))
            opened = getattr(p, "opened_at", None) or getattr(p, "open_time_utc", None) or ""
            if want_open:
                rows.append({
                    "id": f"live_options_{pid}",
                    "symbol": sym,
                    "instrument_type": itype,
                    "is_paper": 0,
                    "qty": qty,
                    "avg_price": getattr(p, "open_credit", None) or getattr(p, "credit_expected", None),
                    "strike": getattr(p, "strike", None),
                    "expiry": (getattr(p, "expiration", None) or getattr(p, "expiry", None) or "")[:10] or None,
                    "right": getattr(p, "option_type", None),
                    "opened_ts": opened,
                    "link_id": pid,
                    "notes": _safe_str(getattr(p, "notes", None)),
                    "tags": None,
                })
            else:
                closed = getattr(p, "closed_at", None) or getattr(p, "close_time_utc", None) or ""
                rows.append({
                    "id": f"live_options_closed_{pid}",
                    "symbol": sym,
                    "instrument_type": itype,
                    "is_paper": 0,
                    "qty": qty,
                    "avg_price": getattr(p, "open_credit", None) or getattr(p, "credit_expected", None),
                    "strike": getattr(p, "strike", None),
                    "expiry": (getattr(p, "expiration", None) or "")[:10] or None,
                    "right": getattr(p, "option_type", None),
                    "opened_ts": opened,
                    "link_id": pid,
                    "notes": _safe_str(getattr(p, "notes", None)),
                    "tags": None,
                    "closed_ts": closed,
                    "realized_pl": getattr(p, "realized_pnl", None),
                    "fees": _fees_from_position(p),
                })
    except Exception as e:
        logger.warning("[R27.9] tracked positions aggregation failed: %s", e)

    # --- Paper ---
    if include_paper:
        try:
            from app.core.paper.paper_store_r270 import paper_list_positions, STATUS_OPEN, STATUS_CLOSED
            status = STATUS_OPEN if want_open else STATUS_CLOSED
            for p in paper_list_positions(status=status, symbol=symbol):
                pid = (p.get("id") or "").strip()
                if not pid:
                    continue
                sym = (p.get("symbol") or "").strip().upper()
                if symbol and (symbol or "").strip().upper() != sym:
                    continue
                strat = (p.get("strategy") or "SHARES").strip().upper()
                itype = INSTRUMENT_SHARES if strat == "SHARES" else (INSTRUMENT_CSP if strat == "CSP" else INSTRUMENT_CC)
                if instrument_type and (instrument_type or "").strip().upper() != itype:
                    continue
                qty = int(p.get("qty") or 0)
                if want_open:
                    rows.append({
                        "id": f"paper_{pid}",
                        "symbol": sym,
                        "instrument_type": itype,
                        "is_paper": 1,
                        "qty": qty,
                        "avg_price": p.get("open_price"),
                        "strike": p.get("strike"),
                        "expiry": (p.get("expiry") or "")[:10] or None,
                        "right": p.get("right"),
                        "opened_ts": (p.get("open_ts") or ""),
                        "link_id": pid,
                        "notes": _safe_str(p.get("notes")),
                        "tags": None,
                    })
                else:
                    rows.append({
                        "id": f"paper_closed_{pid}",
                        "symbol": sym,
                        "instrument_type": itype,
                        "is_paper": 1,
                        "qty": qty,
                        "avg_price": p.get("open_price"),
                        "strike": p.get("strike"),
                        "expiry": (p.get("expiry") or "")[:10] or None,
                        "right": p.get("right"),
                        "opened_ts": (p.get("open_ts") or ""),
                        "link_id": pid,
                        "notes": _safe_str(p.get("notes")),
                        "tags": None,
                        "closed_ts": (p.get("close_ts") or ""),
                        "realized_pl": p.get("realized_pl"),
                        "fees": (float(p.get("open_fees") or 0) + float(p.get("close_fees") or 0)) or None,
                    })
        except Exception as e:
            logger.warning("[R27.9] paper store aggregation failed: %s", e)

    # Deterministic sort
    if want_open:
        rows.sort(key=_sort_key_open)
    else:
        rows.sort(key=_sort_key_closed)

    # Sanitize so no FAIL_/WARN_ in any value
    return [_safe_dict(r) for r in rows]


def get_positions_unified_health() -> Dict[str, Any]:
    """Return health block for system-health: open_count, closed_count, last_build_ts (safe labels only)."""
    from datetime import datetime, timezone
    try:
        open_list = build_unified_positions(state="open", include_paper=True)
        closed_list = build_unified_positions(state="closed", include_paper=True)
        return {
            "open_count": len(open_list),
            "closed_count": len(closed_list),
            "last_build_ts": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("[R27.9] health build failed: %s", e)
        return {
            "open_count": 0,
            "closed_count": 0,
            "last_build_ts": datetime.now(timezone.utc).isoformat(),
        }
