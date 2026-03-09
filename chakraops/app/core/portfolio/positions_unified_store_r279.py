# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R27.9: Unified positions store — read-only aggregation from live shares, live options, paper. Safe labels only."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_REBUILD_LOCK = threading.Lock()  # Non-blocking acquire = "rebuild already running"
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


# --- R28.7: Rebuild unified positions (manual, operator-triggered) ---

def _rebuild_state_path() -> Path:
    """Path for out/positions_unified_rebuild_state.json. Safe labels only in file."""
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "positions_unified_rebuild_state.json"


def _write_rebuild_state(data: Dict[str, Any]) -> None:
    """Persist only status, status_label, timestamps, counts. No FAIL/WARN/PASS. Caller must pass safe values only."""
    safe = {
        "status": data.get("status") or "OK",
        "status_label": data.get("status_label") or "OK",
    }
    for k in ("last_rebuild_at_utc", "last_rebuild_open_count", "last_rebuild_closed_count", "last_include_paper"):
        if k in data:
            safe[k] = data[k]
    path = _rebuild_state_path()
    try:
        from app.core.io.atomic import atomic_write_json
        atomic_write_json(path, safe, indent=0)
    except Exception as e:
        logger.warning("[R28.7] Failed to write rebuild state: %s", e)


def load_rebuild_state() -> Optional[Dict[str, Any]]:
    """Load rebuild state for system-health. Returns None if file missing."""
    path = _rebuild_state_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[R28.7] Failed to load rebuild state: %s", e)
        return None


def get_positions_unified_rebuild_health() -> Dict[str, Any]:
    """R28.7: System-health block positions_unified_rebuild. Safe labels only."""
    state = load_rebuild_state()
    if not state or not isinstance(state, dict):
        return {
            "status": "OK",
            "status_label": "OK",
            "last_rebuild_at_utc": None,
            "last_rebuild_open_count": None,
            "last_rebuild_closed_count": None,
            "last_include_paper": None,
        }
    return {
        "status": state.get("status") or "OK",
        "status_label": state.get("status_label") or "OK",
        "last_rebuild_at_utc": state.get("last_rebuild_at_utc"),
        "last_rebuild_open_count": state.get("last_rebuild_open_count"),
        "last_rebuild_closed_count": state.get("last_rebuild_closed_count"),
        "last_include_paper": state.get("last_include_paper"),
    }


def rebuild_positions_unified(include_paper: bool = True) -> Dict[str, Any]:
    """
    R28.7: Wipe and rebuild positions_open/positions_closed from authoritative sources.
    Single-process lock; deterministic ordering; safe-only return. No notifications, no decision artifacts.
    """
    from datetime import datetime, timezone

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    if not _REBUILD_LOCK.acquire(blocking=False):
        return {
            "status": "Review",
            "status_label": "Rebuild already running",
            "rebuilt_open": 0,
            "rebuilt_closed": 0,
            "include_paper": include_paper,
            "started_at_utc": _now(),
            "finished_at_utc": _now(),
        }

    started_at_utc = _now()
    try:
        init_db()
        open_list = build_unified_positions(state="open", include_paper=include_paper)
        closed_list = build_unified_positions(state="closed", include_paper=include_paper)

        with _LOCK:
            conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
            try:
                conn.execute("DELETE FROM positions_open")
                conn.execute("DELETE FROM positions_closed")
                for r in open_list:
                    conn.execute(
                        """INSERT INTO positions_open (
                            id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            r.get("id"), r.get("symbol"), r.get("instrument_type"), int(r.get("is_paper") or 0),
                            int(r.get("qty") or 0), r.get("avg_price"), r.get("strike"), r.get("expiry"), r.get("right"),
                            (r.get("opened_ts") or "")[:26], r.get("link_id"), r.get("notes"), r.get("tags"),
                        ),
                    )
                for r in closed_list:
                    conn.execute(
                        """INSERT INTO positions_closed (
                            id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags,
                            closed_ts, realized_pl, fees
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            r.get("id"), r.get("symbol"), r.get("instrument_type"), int(r.get("is_paper") or 0),
                            int(r.get("qty") or 0), r.get("avg_price"), r.get("strike"), r.get("expiry"), r.get("right"),
                            (r.get("opened_ts") or "")[:26], r.get("link_id"), r.get("notes"), r.get("tags"),
                            (r.get("closed_ts") or "")[:26], r.get("realized_pl"), r.get("fees"),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()

        finished_at_utc = _now()
        _write_rebuild_state({
            "status": "OK",
            "status_label": "OK",
            "last_rebuild_at_utc": finished_at_utc,
            "last_rebuild_open_count": len(open_list),
            "last_rebuild_closed_count": len(closed_list),
            "last_include_paper": include_paper,
        })
        return {
            "status": "OK",
            "status_label": "OK",
            "rebuilt_open": len(open_list),
            "rebuilt_closed": len(closed_list),
            "include_paper": include_paper,
            "started_at_utc": started_at_utc,
            "finished_at_utc": finished_at_utc,
        }
    except Exception as e:
        logger.exception("[R28.7] Rebuild failed: %s", e)
        finished_at_utc = _now()
        _write_rebuild_state({
            "status": "Review",
            "status_label": "Rebuild failed",
            "last_rebuild_at_utc": finished_at_utc,
            "last_rebuild_open_count": 0,
            "last_rebuild_closed_count": 0,
            "last_include_paper": include_paper,
        })
        return {
            "status": "Review",
            "status_label": "Rebuild failed",
            "rebuilt_open": 0,
            "rebuilt_closed": 0,
            "include_paper": include_paper,
            "started_at_utc": started_at_utc,
            "finished_at_utc": finished_at_utc,
        }
    finally:
        try:
            _REBUILD_LOCK.release()
        except Exception:
            pass


# --- R28.0: Paper write mirror (idempotent upsert) ---

def _paper_pos_to_instrument_type(p: Dict[str, Any]) -> str:
    strat = (p.get("strategy") or "SHARES").strip().upper()
    if strat == "SHARES":
        return INSTRUMENT_SHARES
    if strat == "CSP":
        return INSTRUMENT_CSP
    if strat == "CC":
        return INSTRUMENT_CC
    return INSTRUMENT_CC  # OPTION fallback


def mirror_paper_open_to_unified(pos: Dict[str, Any]) -> None:
    """R28.0: Idempotent upsert of paper open position into positions_open. Stable id = paper_{pos[id]}."""
    pid = (pos.get("id") or "").strip()
    if not pid:
        return
    init_db()
    sym = (pos.get("symbol") or "").strip().upper()
    itype = _paper_pos_to_instrument_type(pos)
    qty = int(pos.get("qty") or 0)
    opened_ts = (pos.get("open_ts") or "")[:26]
    if not opened_ts:
        return
    row_id = f"paper_{pid}"
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO positions_open (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, sym, itype, qty,
                    pos.get("open_price"), pos.get("strike"), (pos.get("expiry") or "")[:10] or None, pos.get("right"),
                    opened_ts, pid, _safe_str(pos.get("notes")), None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.0] mirrored paper open %s to unified", row_id)


def mirror_paper_close_to_unified(pos: Dict[str, Any]) -> None:
    """R28.0: Idempotent upsert of paper closed position into positions_closed; remove from positions_open. Stable id = paper_closed_{pos[id]}."""
    pid = (pos.get("id") or "").strip()
    if not pid:
        return
    init_db()
    sym = (pos.get("symbol") or "").strip().upper()
    itype = _paper_pos_to_instrument_type(pos)
    qty = int(pos.get("qty") or 0)
    opened_ts = (pos.get("open_ts") or "")[:26]
    closed_ts = (pos.get("close_ts") or "")[:26]
    if not closed_ts:
        return
    open_row_id = f"paper_{pid}"
    closed_row_id = f"paper_closed_{pid}"
    fees = (float(pos.get("open_fees") or 0) + float(pos.get("close_fees") or 0)) or None
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute("DELETE FROM positions_open WHERE id = ?", (open_row_id,))
            conn.execute(
                """INSERT OR REPLACE INTO positions_closed (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags,
                    closed_ts, realized_pl, fees
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    closed_row_id, sym, itype, qty,
                    pos.get("open_price"), pos.get("strike"), (pos.get("expiry") or "")[:10] or None, pos.get("right"),
                    opened_ts, pid, _safe_str(pos.get("notes")), None,
                    closed_ts, pos.get("realized_pl"), fees,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.0] mirrored paper close %s to unified", closed_row_id)


def get_positions_unified_reconcile_health() -> Dict[str, Any]:
    """R28.0/R28.4: Reconcile health — paper + live open source counts vs unified DB. Status OK or Review (safe labels only; no FAIL/WARN)."""
    paper_open_count = 0
    paper_closed_count = 0
    live_shares_open_count = 0
    live_options_open_count = 0
    try:
        from app.core.paper.paper_store_r270 import paper_list_positions, STATUS_OPEN, STATUS_CLOSED
        paper_open = paper_list_positions(status=STATUS_OPEN)
        paper_closed = paper_list_positions(status=STATUS_CLOSED)
        paper_open_count = len([p for p in paper_open if (p.get("id") or "").strip()])
        paper_closed_count = len([p for p in paper_closed if (p.get("id") or "").strip()])
    except Exception as e:
        logger.warning("[R28.0] reconcile: paper source failed: %s", e)
    try:
        from app.core.accounts.holdings_db import list_share_positions, _DEFAULT_ACCOUNT_ID
        live_shares = list_share_positions(_DEFAULT_ACCOUNT_ID)
        live_shares_open_count = len([s for s in live_shares if int(s.get("quantity") or 0) > 0])
    except Exception as e:
        logger.warning("[R28.4] reconcile: live shares source failed: %s", e)
    try:
        from app.core.positions.store import list_positions as list_tracked
        live_options = list_tracked(status="OPEN")
        live_options_open_count = len([p for p in live_options if (getattr(p, "strategy", "") or "").strip().upper() in ("CSP", "CC")])
    except Exception as e:
        logger.warning("[R28.4] reconcile: live options source failed: %s", e)
    init_db()
    unified_open_paper = 0
    unified_closed_paper = 0
    unified_open_live_shares_count = 0
    unified_open_live_options_count = 0
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            unified_open_paper = conn.execute(
                "SELECT COUNT(*) FROM positions_open WHERE is_paper = 1"
            ).fetchone()[0]
            unified_closed_paper = conn.execute(
                "SELECT COUNT(*) FROM positions_closed WHERE is_paper = 1"
            ).fetchone()[0]
            unified_open_live_shares_count = conn.execute(
                "SELECT COUNT(*) FROM positions_open WHERE is_paper = 0 AND instrument_type = ?",
                (INSTRUMENT_SHARES,),
            ).fetchone()[0]
            unified_open_live_options_count = conn.execute(
                "SELECT COUNT(*) FROM positions_open WHERE is_paper = 0 AND instrument_type IN (?, ?)",
                (INSTRUMENT_CSP, INSTRUMENT_CC),
            ).fetchone()[0]
        finally:
            conn.close()
    paper_ok = unified_open_paper == paper_open_count and unified_closed_paper == paper_closed_count
    live_shares_ok = unified_open_live_shares_count == live_shares_open_count
    live_options_ok = unified_open_live_options_count == live_options_open_count
    status = "OK" if (paper_ok and live_shares_ok and live_options_ok) else "Review"
    return {
        "paper_open_count": paper_open_count,
        "paper_closed_count": paper_closed_count,
        "unified_open_paper_count": unified_open_paper,
        "unified_closed_paper_count": unified_closed_paper,
        "live_shares_open_count": live_shares_open_count,
        "live_options_open_count": live_options_open_count,
        "unified_open_live_shares_count": unified_open_live_shares_count,
        "unified_open_live_options_count": unified_open_live_options_count,
        "status": status,
    }


# --- R28.1: Live close/roll mirror (idempotent) ---

def _live_options_pos_to_instrument_type(p: Dict[str, Any]) -> str:
    strat = (p.get("strategy") or "").strip().upper()
    if strat == "CSP":
        return INSTRUMENT_CSP
    if strat == "CC":
        return INSTRUMENT_CC
    return INSTRUMENT_CC  # OPTION fallback


def mirror_live_close_to_unified(payload_or_position: Dict[str, Any]) -> None:
    """R28.1: Idempotent mirror of a live close into positions_closed. Handles shares (dict from close_share_position) or options (Position.to_dict() or equivalent)."""
    p = payload_or_position if isinstance(payload_or_position, dict) else getattr(payload_or_position, "to_dict", lambda: {})()
    if not p:
        return
    # Options: has position_id and strategy CSP/CC
    position_id = (p.get("position_id") or p.get("id") or "").strip()
    strategy = (p.get("strategy") or "").strip().upper()
    is_options = bool(position_id and strategy in ("CSP", "CC"))
    if is_options:
        _mirror_live_options_close(p)
        return
    # Shares: id = closed row id, symbol, quantity, opened_at, closed_at, exit_price, realized_pnl
    closed_id = (p.get("id") or "").strip()
    if not closed_id or not (p.get("symbol") or "").strip():
        return
    _mirror_live_shares_close(p, closed_id)


def _mirror_live_shares_close(p: Dict[str, Any], closed_id: str) -> None:
    """Mirror live shares closed row. Stable id = live_shares_closed_{closed_id}. R28.4: Remove corresponding open row (one per symbol for live SHARES)."""
    sym = (p.get("symbol") or "").strip().upper()
    if not sym:
        return
    qty = int(p.get("quantity") or 0)
    opened_ts = (p.get("opened_at") or "")[:26]
    closed_ts = (p.get("closed_at") or "")[:26]
    if not closed_ts:
        return
    init_db()
    row_id = f"live_shares_closed_{closed_id}"
    avg_price = p.get("avg_cost") or p.get("exit_price")
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute(
                "DELETE FROM positions_open WHERE symbol = ? AND is_paper = 0 AND instrument_type = ?",
                (sym, INSTRUMENT_SHARES),
            )
            conn.execute(
                """INSERT OR REPLACE INTO positions_closed (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags,
                    closed_ts, realized_pl, fees
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, sym, INSTRUMENT_SHARES, qty, avg_price, None, None, None, opened_ts, closed_id, _safe_str(p.get("close_notes")), None,
                    closed_ts, p.get("realized_pnl"), None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.1] mirrored live shares close %s to unified", row_id)


def _mirror_live_options_close(p: Dict[str, Any]) -> None:
    """Mirror live options closed: remove from positions_open, upsert into positions_closed. Stable id = live_options_closed_{position_id}."""
    pid = (p.get("position_id") or p.get("id") or "").strip()
    if not pid:
        return
    init_db()
    sym = (p.get("symbol") or "").strip().upper()
    itype = _live_options_pos_to_instrument_type(p)
    contracts = int(p.get("contracts") or 0)
    qty = contracts * 100 if contracts else (int(p.get("quantity") or 0))
    opened_ts = (p.get("opened_at") or p.get("open_time_utc") or "")[:26]
    closed_ts = (p.get("closed_at") or p.get("close_time_utc") or "")[:26]
    if not closed_ts:
        return
    open_row_id = f"live_options_{pid}"
    closed_row_id = f"live_options_closed_{pid}"
    open_f = float(p.get("open_fees") or 0)
    close_f = float(p.get("close_fees") or 0)
    fees = (open_f + close_f) or None
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute("DELETE FROM positions_open WHERE id = ?", (open_row_id,))
            conn.execute(
                """INSERT OR REPLACE INTO positions_closed (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags,
                    closed_ts, realized_pl, fees
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    closed_row_id, sym, itype, qty,
                    p.get("open_credit") or p.get("credit_expected"), p.get("strike"), (p.get("expiration") or p.get("expiry") or "")[:10] or None, p.get("option_type") or p.get("right"),
                    opened_ts, pid, _safe_str(p.get("notes")), None,
                    closed_ts, p.get("realized_pnl"), fees,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.1] mirrored live options close %s to unified", closed_row_id)


def mirror_live_shares_open_to_unified(share_position: Dict[str, Any]) -> None:
    """R28.4: Idempotent mirror of a live SHARES open position into positions_open. Stable id = live_shares_{id}. Source=LIVE."""
    sid = (share_position.get("id") or "").strip()
    if not sid:
        return
    sym = (share_position.get("symbol") or "").strip().upper()
    if not sym:
        return
    qty = int(share_position.get("quantity") or 0)
    if qty <= 0:
        return
    opened_ts = (share_position.get("opened_at") or share_position.get("created_at") or "")[:26]
    if not opened_ts:
        return
    init_db()
    row_id = f"live_shares_{sid}"
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO positions_open (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, sym, INSTRUMENT_SHARES, qty,
                    share_position.get("avg_cost"), None, None, None,
                    opened_ts, sid, _safe_str(share_position.get("notes")), None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.4] mirrored live shares open %s to unified", row_id)


def mirror_live_open_to_unified(payload_or_position: Dict[str, Any]) -> None:
    """R28.1: Idempotent mirror of a live options OPEN position into positions_open (e.g. after roll). Stable id = live_options_{position_id}. R28.4: For SHARES use mirror_live_shares_open_to_unified."""
    p = payload_or_position if isinstance(payload_or_position, dict) else getattr(payload_or_position, "to_dict", lambda: {})()
    if not p:
        return
    pid = (p.get("position_id") or p.get("id") or "").strip()
    if not pid:
        return
    strat = (p.get("strategy") or "").strip().upper()
    if strat not in ("CSP", "CC"):
        return
    init_db()
    sym = (p.get("symbol") or "").strip().upper()
    itype = _live_options_pos_to_instrument_type(p)
    contracts = int(p.get("contracts") or 0)
    qty = contracts * 100 if contracts else (int(p.get("quantity") or 0))
    opened_ts = (p.get("opened_at") or p.get("open_time_utc") or "")[:26]
    if not opened_ts:
        return
    row_id = f"live_options_{pid}"
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO positions_open (
                    id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags
                ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, sym, itype, qty,
                    p.get("open_credit") or p.get("credit_expected"), p.get("strike"), (p.get("expiration") or p.get("expiry") or "")[:10] or None, p.get("option_type") or p.get("right"),
                    opened_ts, pid, _safe_str(p.get("notes")), None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    logger.debug("[R28.1] mirrored live options open %s to unified", row_id)


def ensure_reconcile_advisory_notification() -> None:
    """R28.1: If reconcile status is Review, ensure exactly one advisory notification (deduped). Safe labels only; no FAIL/WARN."""
    try:
        health = get_positions_unified_reconcile_health()
        if (health.get("status") or "").strip() != "Review":
            return
    except Exception as e:
        logger.warning("[R28.1] reconcile health check failed: %s", e)
        return
    try:
        from app.api.notifications_store import load_notifications, append_notification
        existing = load_notifications(limit=200, state_filter=None, type_filter="POSITIONS_RECONCILE_REVIEW")
        for rec in existing:
            if rec.get("state") in ("NEW", "ACKED"):
                return  # Already have an active one; do not create another
        message = "Unified positions reconcile needs attention (counts differ)."
        append_notification("INFO", "POSITIONS_RECONCILE_REVIEW", message, symbol=None, details={"advisory": True})
    except Exception as e:
        logger.warning("[R28.1] reconcile advisory notification failed: %s", e)
