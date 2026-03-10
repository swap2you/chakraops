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
_INTEGRITY_CHECK_LOCK = threading.Lock()  # R29.3: non-blocking = "check already running"
_OVERRIDE_PATH: Optional[Path] = None

# R29.3: Staleness threshold for integrity check (hours)
_INTEGRITY_CHECK_STALE_HOURS = 24
# R29.4: History and sample caps (deterministic)
_INTEGRITY_CHECK_HISTORY_CAP = 10
_INTEGRITY_CHECK_SAMPLE_ITEMS_CAP = 20

INSTRUMENT_SHARES = "SHARES"
INSTRUMENT_CSP = "CSP"
INSTRUMENT_CC = "CC"

# Prohibited in API responses (non-negotiable)
_FAIL_WARN_PATTERN = re.compile(r"FAIL_|WARN_", re.I)
_FORBIDDEN_TOKENS = re.compile(r"\b(FAIL|WARN|PASS)\b", re.I)


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
        return ""
    return s


def _sanitize_display_str(val: Any) -> str:
    """R29.4: No FAIL/WARN/PASS or FAIL_/WARN_ in display strings. Replace forbidden tokens; strip bad substrings."""
    if val is None:
        return ""
    s = str(val).strip()
    s = _FORBIDDEN_TOKENS.sub("", s)
    if _FAIL_WARN_PATTERN.search(s):
        return ""
    return s.strip() or ""


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
    """R28.7/R29.0: System-health block positions_unified_rebuild. Safe labels only. finished_at_utc alias for staleness."""
    state = load_rebuild_state()
    if not state or not isinstance(state, dict):
        return {
            "status": "OK",
            "status_label": "OK",
            "last_rebuild_at_utc": None,
            "finished_at_utc": None,
            "last_rebuild_open_count": None,
            "last_rebuild_closed_count": None,
            "last_include_paper": None,
        }
    last_ts = state.get("last_rebuild_at_utc")
    return {
        "status": state.get("status") or "OK",
        "status_label": state.get("status_label") or "OK",
        "last_rebuild_at_utc": last_ts,
        "finished_at_utc": last_ts,
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


# --- R28.9: DB-first read (what is stored; no source recompute) ---

def read_positions_unified_from_db(
    state: str = "open",
    include_paper: bool = True,
    instrument_type: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    R28.9: Read directly from unified SQLite (positions_open or positions_closed).
    No recompute from sources. Deterministic ordering; safe labels only; no writes.
    """
    limit = max(0, min(int(limit), 2000))
    want_open = (state or "open").strip().lower() != "closed"
    init_db()
    rows: List[Dict[str, Any]] = []
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            conditions: List[str] = []
            params: List[Any] = []
            if not include_paper:
                conditions.append("is_paper = 0")
            if symbol:
                conditions.append("symbol = ?")
                params.append((symbol or "").strip().upper())
            if instrument_type:
                conditions.append("instrument_type = ?")
                params.append((instrument_type or "").strip().upper())
            where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
            if want_open:
                sql = "SELECT id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags FROM positions_open" + where_clause
                cursor = conn.execute(sql, params)
                for row in cursor.fetchall():
                    rows.append({
                        "id": row[0],
                        "symbol": (row[1] or "").strip().upper(),
                        "instrument_type": row[2] or "",
                        "is_paper": int(row[3] or 0),
                        "qty": int(row[4] or 0),
                        "avg_price": row[5],
                        "strike": row[6],
                        "expiry": (row[7] or "")[:10] if row[7] else None,
                        "right": row[8],
                        "opened_ts": (row[9] or "")[:26],
                        "link_id": row[10],
                        "notes": _safe_str(row[11]),
                        "tags": row[12],
                    })
            else:
                sql = "SELECT id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags, closed_ts, realized_pl, fees FROM positions_closed" + where_clause
                cursor = conn.execute(sql, params)
                for row in cursor.fetchall():
                    rows.append({
                        "id": row[0],
                        "symbol": (row[1] or "").strip().upper(),
                        "instrument_type": row[2] or "",
                        "is_paper": int(row[3] or 0),
                        "qty": int(row[4] or 0),
                        "avg_price": row[5],
                        "strike": row[6],
                        "expiry": (row[7] or "")[:10] if row[7] else None,
                        "right": row[8],
                        "opened_ts": (row[9] or "")[:26],
                        "link_id": row[10],
                        "notes": _safe_str(row[11]),
                        "tags": row[12],
                        "closed_ts": (row[13] or "")[:26],
                        "realized_pl": row[14],
                        "fees": row[15],
                    })
        finally:
            conn.close()
    if want_open:
        rows.sort(key=_sort_key_open)
    else:
        rows.sort(key=_sort_key_closed)
    items = [_safe_dict(r) for r in rows[:limit]]
    return {
        "status": "OK",
        "status_label": "OK",
        "count": len(items),
        "items": items,
    }


# --- R28.8: Reconcile diff (read-only; operator explainability) ---

def _read_positions_open_from_db(symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read positions_open from unified DB into list of dicts (same shape as build_unified_positions). Deterministic order."""
    init_db()
    rows: List[Dict[str, Any]] = []
    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            if symbol:
                sym = (symbol or "").strip().upper()
                cursor = conn.execute(
                    "SELECT id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags FROM positions_open WHERE symbol = ?",
                    (sym,),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right, opened_ts, link_id, notes, tags FROM positions_open",
                )
            for row in cursor.fetchall():
                rows.append({
                    "id": row[0],
                    "symbol": (row[1] or "").strip().upper(),
                    "instrument_type": row[2] or "",
                    "is_paper": int(row[3] or 0),
                    "qty": int(row[4] or 0),
                    "avg_price": row[5],
                    "strike": row[6],
                    "expiry": (row[7] or "")[:10] if row[7] else None,
                    "right": row[8],
                    "opened_ts": (row[9] or "")[:26],
                    "link_id": row[10],
                    "notes": _safe_str(row[11]),
                    "tags": row[12],
                })
        finally:
            conn.close()
    rows.sort(key=_sort_key_open)
    return [_safe_dict(r) for r in rows]


def _diff_sort_key(item: Dict[str, Any]) -> tuple:
    """Stable sort for diff items: symbol, instrument_type, id."""
    sym = (item.get("symbol") or "").strip().upper()
    itype = (item.get("instrument_type") or "").upper()
    pid = (item.get("id") or "").strip()
    return (sym, itype, pid)


def get_reconcile_diff(
    include_paper: bool = True,
    symbol: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """
    R28.8: Read-only diff of authoritative sources vs unified DB (open positions).
    Returns missing_in_unified, extra_in_unified, mismatched (key field differences).
    Deterministic ordering; safe labels only; no writes.
    """
    expected = build_unified_positions(state="open", include_paper=include_paper, symbol=symbol)
    unified = _read_positions_open_from_db(symbol=symbol)
    expected_by_id = {r["id"]: r for r in expected}
    unified_by_id = {r["id"]: r for r in unified}
    expected_ids = set(expected_by_id)
    unified_ids = set(unified_by_id)
    missing = [expected_by_id[eid] for eid in expected_ids if eid not in unified_ids]
    extra = [unified_by_id[uid] for uid in unified_ids if uid not in expected_ids]
    mismatched: List[Dict[str, Any]] = []
    for eid in expected_ids & unified_ids:
        exp = expected_by_id[eid]
        uni = unified_by_id[eid]
        diff_fields: List[str] = []
        if int(exp.get("qty") or 0) != int(uni.get("qty") or 0):
            diff_fields.append("qty")
        if (exp.get("instrument_type") or "").strip() != (uni.get("instrument_type") or "").strip():
            diff_fields.append("instrument_type")
        if float(exp.get("strike") or 0) != float(uni.get("strike") or 0):
            diff_fields.append("strike")
        if ((exp.get("expiry") or "")[:10] or None) != ((uni.get("expiry") or "")[:10] or None):
            diff_fields.append("expiry")
        if (exp.get("opened_ts") or "")[:26] != (uni.get("opened_ts") or "")[:26]:
            diff_fields.append("opened_ts")
        if diff_fields:
            mismatched.append({
                "id": exp["id"],
                "symbol": exp.get("symbol"),
                "instrument_type": exp.get("instrument_type"),
                "is_paper": exp.get("is_paper"),
                "fields_diff": diff_fields,
            })
    items: List[Dict[str, Any]] = []
    for r in missing:
        items.append({"kind": "missing", "id": r["id"], "symbol": r.get("symbol"), "instrument_type": r.get("instrument_type"), "is_paper": r.get("is_paper")})
    for r in extra:
        items.append({"kind": "extra", "id": r["id"], "symbol": r.get("symbol"), "instrument_type": r.get("instrument_type"), "is_paper": r.get("is_paper")})
    for r in mismatched:
        items.append({"kind": "mismatched", "id": r["id"], "symbol": r.get("symbol"), "instrument_type": r.get("instrument_type"), "is_paper": r.get("is_paper"), "fields_diff": r.get("fields_diff", [])})
    items.sort(key=_diff_sort_key)
    items = items[: max(0, limit)]
    status = "OK" if (len(missing) == 0 and len(extra) == 0 and len(mismatched) == 0) else "Review"
    status_label = "OK" if status == "OK" else "Differences found"
    return {
        "status": status,
        "status_label": status_label,
        "missing_count": len(missing),
        "extra_count": len(extra),
        "mismatched_count": len(mismatched),
        "items": [_safe_dict(i) for i in items],
    }


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


# --- R29.3: Integrity check (manual; staleness + reconcile; optional advisory) ---

def _integrity_check_state_path() -> Path:
    """Path for out/positions_unified_integrity_check_state.json. Safe fields only."""
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "positions_unified_integrity_check_state.json"


def _sanitize_sample_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """R29.4: One diff item with all string values sanitized (no FAIL/WARN/PASS or FAIL_/WARN_)."""
    out: Dict[str, Any] = {}
    for k, v in item.items():
        if isinstance(v, str):
            out[k] = _sanitize_display_str(v)
        elif isinstance(v, list):
            out[k] = [_sanitize_display_str(x) if isinstance(x, str) else x for x in v]
        else:
            out[k] = v
    return out


def _write_integrity_check_state(data: Dict[str, Any]) -> None:
    """R29.3/R29.4: Persist only safe fields; no FAIL/WARN/PASS. State has last + history (capped)."""
    rec = data.get("reconcile") or {}
    sample_raw = data.get("sample_items") or []
    sample = [_sanitize_sample_item(i) for i in sample_raw[: _INTEGRITY_CHECK_SAMPLE_ITEMS_CAP]]
    sample.sort(key=_diff_sort_key)
    last_entry = {
        "status": data.get("status") or "OK",
        "status_label": data.get("status_label") or "OK",
        "started_at_utc": data.get("started_at_utc"),
        "finished_at_utc": data.get("checked_at_utc"),
        "missing_count": rec.get("missing_count", 0),
        "extra_count": rec.get("extra_count", 0),
        "mismatched_count": rec.get("mismatched_count", 0),
        "sample_items": sample,
    }
    path = _integrity_check_state_path()
    try:
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        history = existing.get("history") or []
        if not isinstance(history, list):
            history = []
        history = [last_entry] + history[: _INTEGRITY_CHECK_HISTORY_CAP - 1]
        payload = {"last": last_entry, "history": history}
        from app.core.io.atomic import atomic_write_json
        atomic_write_json(path, payload, indent=0)
    except Exception as e:
        logger.warning("[R29.3] Failed to write integrity check state: %s", e)


def load_integrity_check_state() -> Optional[Dict[str, Any]]:
    """Load last integrity check state for system-health."""
    path = _integrity_check_state_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("[R29.3] Failed to load integrity check state: %s", e)
        return None


def ensure_positions_integrity_advisory_notification() -> None:
    """R29.3: If no active NEW/ACKED notification of type POSITIONS_INTEGRITY_REVIEW, create one. Safe message only."""
    try:
        from app.api.notifications_store import load_notifications, append_notification
        existing = load_notifications(limit=200, state_filter=None, type_filter="POSITIONS_INTEGRITY_REVIEW")
        for rec in existing:
            if rec.get("state") in ("NEW", "ACKED"):
                return
        message = "Positions integrity check found issues (stored may be stale or reconcile differs)."
        append_notification("INFO", "POSITIONS_INTEGRITY_REVIEW", message, symbol=None, details={"advisory": True})
    except Exception as e:
        logger.warning("[R29.3] integrity advisory notification failed: %s", e)


def run_positions_unified_integrity_check(include_paper: bool = True) -> Dict[str, Any]:
    """
    R29.3: Manual integrity check — staleness (from rebuild health) + reconcile diff summary.
    Returns safe-label result only. Optionally creates one advisory notification when Review (deduped).
    Does NOT write decision_latest or any decision artifacts.
    """
    from datetime import datetime, timezone, timedelta

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    if not _INTEGRITY_CHECK_LOCK.acquire(blocking=False):
        return {
            "ok": False,
            "status": "Review",
            "status_label": "Check already running",
            "include_paper": include_paper,
            "stale": False,
            "reconcile": {"status": "OK", "status_label": "OK", "missing_count": 0, "extra_count": 0, "mismatched_count": 0},
            "checked_at_utc": _now(),
        }

    try:
        started_at = _now()
        checked_at = _now()
        rebuild_health = get_positions_unified_rebuild_health()
        finished_at = rebuild_health.get("finished_at_utc") or rebuild_health.get("last_rebuild_at_utc")
        stale = False
        status_label = "OK"
        if not finished_at or not isinstance(finished_at, str):
            stale = True
            status_label = "No rebuild recorded"
        else:
            try:
                dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
                if age_h > _INTEGRITY_CHECK_STALE_HOURS:
                    stale = True
                    status_label = "Stored positions may be stale"
            except (ValueError, TypeError):
                stale = True
                status_label = "No rebuild recorded"

        reconcile = get_reconcile_diff(include_paper=include_paper, symbol=None, limit=50)
        rec_status = (reconcile.get("status") or "OK").strip()
        rec_label = reconcile.get("status_label") or "OK"
        if rec_status == "Review":
            if not stale:
                status_label = rec_label
            stale = stale or (rec_status == "Review")
        overall_status = "Review" if (stale or rec_status == "Review") else "OK"
        if not stale and overall_status == "OK":
            status_label = "OK"

        items = list(reconcile.get("items") or [])
        items.sort(key=_diff_sort_key)
        sample_items = items[: _INTEGRITY_CHECK_SAMPLE_ITEMS_CAP]

        result = {
            "ok": overall_status == "OK",
            "status": overall_status,
            "status_label": status_label,
            "include_paper": include_paper,
            "stale": stale,
            "started_at_utc": started_at,
            "reconcile": {
                "status": rec_status,
                "status_label": rec_label,
                "missing_count": reconcile.get("missing_count", 0),
                "extra_count": reconcile.get("extra_count", 0),
                "mismatched_count": reconcile.get("mismatched_count", 0),
            },
            "checked_at_utc": checked_at,
            "sample_items": sample_items,
        }
        _write_integrity_check_state(result)
        if overall_status == "Review":
            ensure_positions_integrity_advisory_notification()
        return result
    finally:
        try:
            _INTEGRITY_CHECK_LOCK.release()
        except Exception:
            pass


def get_positions_unified_integrity_check_health() -> Dict[str, Any]:
    """R29.3/R29.4: System-health block positions_unified_integrity_check. Read-only from state file; safe only."""
    state = load_integrity_check_state()
    if not state or not isinstance(state, dict):
        return {
            "last_checked_at_utc": None,
            "last_status": "OK",
            "last_status_label": "OK",
            "last_stale": False,
            "last_reconcile_missing_count": None,
            "last_reconcile_extra_count": None,
            "last_reconcile_mismatched_count": None,
            "last_started_at_utc": None,
            "last_sample_items": None,
        }
    last = state.get("last")
    if isinstance(last, dict):
        return {
            "last_checked_at_utc": last.get("finished_at_utc"),
            "last_status": last.get("status") or "OK",
            "last_status_label": last.get("status_label") or "OK",
            "last_stale": state.get("last_stale", False),
            "last_reconcile_missing_count": last.get("missing_count"),
            "last_reconcile_extra_count": last.get("extra_count"),
            "last_reconcile_mismatched_count": last.get("mismatched_count"),
            "last_started_at_utc": last.get("started_at_utc"),
            "last_sample_items": last.get("sample_items"),
        }
    return {
        "last_checked_at_utc": state.get("last_checked_at_utc"),
        "last_status": state.get("last_status") or "OK",
        "last_status_label": state.get("last_status_label") or "OK",
        "last_stale": state.get("last_stale", False),
        "last_reconcile_missing_count": state.get("last_reconcile_missing_count"),
        "last_reconcile_extra_count": state.get("last_reconcile_extra_count"),
        "last_reconcile_mismatched_count": state.get("last_reconcile_mismatched_count"),
        "last_started_at_utc": None,
        "last_sample_items": None,
    }


def get_positions_unified_integrity_check_result() -> Dict[str, Any]:
    """R29.4: Read-only last result + history for GET /api/ui/positions/unified/integrity-check. Deterministic ordering."""
    state = load_integrity_check_state()
    if not state or not isinstance(state, dict):
        return {
            "status": "OK",
            "status_label": "OK",
            "last": None,
            "history": [],
        }
    last = state.get("last")
    history = state.get("history") or []
    if not isinstance(history, list):
        history = []
    if isinstance(last, dict):
        return {
            "status": last.get("status") or "OK",
            "status_label": last.get("status_label") or "OK",
            "last": last,
            "history": history[: _INTEGRITY_CHECK_HISTORY_CAP],
        }
    last_derived = {
        "status": state.get("last_status") or "OK",
        "status_label": state.get("last_status_label") or "OK",
        "started_at_utc": None,
        "finished_at_utc": state.get("last_checked_at_utc"),
        "missing_count": state.get("last_reconcile_missing_count"),
        "extra_count": state.get("last_reconcile_extra_count"),
        "mismatched_count": state.get("last_reconcile_mismatched_count"),
        "sample_items": [],
    }
    return {
        "status": last_derived["status"],
        "status_label": last_derived["status_label"],
        "last": last_derived,
        "history": [],
    }
