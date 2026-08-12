# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-ABCD Batch A — canonical LIVE position lenses.

Fresh authenticated broker snapshot is LIVE authority when available.
Manual/unified/paper/history remain labeled and never masquerade as LIVE.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LENS_LIVE_BROKER_EQUITY = "LIVE_BROKER_EQUITY_POSITIONS"
LENS_LIVE_BROKER_OPTION = "LIVE_BROKER_OPTION_POSITIONS"
LENS_LIVE_TOTAL = "LIVE_TOTAL_POSITIONS"
LENS_PAPER_OPEN = "PAPER_OPEN_POSITIONS"
LENS_HISTORICAL_CLOSED = "HISTORICAL_CLOSED_POSITIONS"
LENS_MANUAL_RECOVERY = "MANUAL_RECOVERY_POSITIONS"
LENS_UNIFIED_STORE_OPEN = "UNIFIED_STORE_OPEN_POSITIONS"  # diagnostic only — not LIVE authority


def build_live_position_lenses(
    *,
    account_alias: str = "acct_individual",
) -> Dict[str, Any]:
    """Return explicit position lenses with counts, provenance, and sizing gate."""
    from app.core.broker.snapshot_store import load_snapshot
    from app.core.broker.status import robinhood_mcp_read_only_status

    snap = load_snapshot(account_alias)
    snap_stale = bool(snap.stale) if snap is not None else True
    status = robinhood_mcp_read_only_status(snapshot_stale=snap_stale if snap is not None else None)
    broker_ready = bool(status.get("ROBINHOOD_MCP_READ_ONLY_AVAILABLE")) and snap is not None
    broker_fresh = bool(
        broker_ready and not snap_stale and bool(getattr(snap, "fetched_at", None))
    )

    equities: List[Dict[str, Any]] = []
    options: List[Dict[str, Any]] = []
    if snap is not None:
        for p in snap.equity_positions or []:
            equities.append(
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "average_cost": p.average_cost,
                    "market_value": p.market_value,
                    "side": p.side,
                    "lens": LENS_LIVE_BROKER_EQUITY,
                    "authority": "broker_snapshot",
                }
            )
        for p in snap.option_positions or []:
            options.append(
                {
                    "symbol": p.symbol,
                    "option_type": p.option_type,
                    "strike": p.strike,
                    "expiration": p.expiration,
                    "quantity": p.quantity,
                    "average_cost": p.average_cost,
                    "side": p.side,
                    "lens": LENS_LIVE_BROKER_OPTION,
                    "authority": "broker_snapshot",
                }
            )

    live_authority = "broker_snapshot" if broker_ready else "unavailable"
    live_state = "FRESH" if broker_fresh else ("STALE" if broker_ready else "UNAVAILABLE")
    if broker_ready and snap_stale:
        live_state = "STALE"

    # LIVE totals only from broker when ready; never from unified orphans.
    live_equity_count = len(equities) if broker_ready else 0
    live_option_count = len(options) if broker_ready else 0
    live_total = live_equity_count + live_option_count if broker_ready else 0

    manual = _manual_recovery_positions()
    paper = _paper_open_positions()
    historical = _historical_closed_count()
    unified_diag = _unified_open_diagnostic()

    sizing_blocked = (not broker_ready) or live_state == "STALE" or live_state == "UNAVAILABLE"

    return {
        "manual_only": True,
        "trade_execution": False,
        "account_alias": account_alias,
        "broker_status": status.get("status"),
        "live_state": live_state,
        "live_authority": live_authority if broker_ready else None,
        "as_of": snap.fetched_at if snap is not None else None,
        "source": snap.source if snap is not None else None,
        "freshness": snap.freshness if snap is not None else None,
        "stale": snap_stale if snap is not None else True,
        "sizing_blocked": sizing_blocked,
        "lenses": {
            LENS_LIVE_BROKER_EQUITY: {
                "label": "Live broker equity positions",
                "count": live_equity_count,
                "items": equities if broker_ready else [],
                "authority": live_authority if broker_ready else None,
            },
            LENS_LIVE_BROKER_OPTION: {
                "label": "Live broker option positions",
                "count": live_option_count,
                "items": options if broker_ready else [],
                "authority": live_authority if broker_ready else None,
            },
            LENS_LIVE_TOTAL: {
                "label": "Live total positions (broker)",
                "count": live_total,
                "authority": live_authority if broker_ready else None,
            },
            LENS_MANUAL_RECOVERY: {
                "label": "Manual recovery holdings (not live)",
                "count": len(manual),
                "items": manual,
                "authority": "manual_holdings",
            },
            LENS_PAPER_OPEN: {
                "label": "Paper open positions",
                "count": len(paper),
                "items": paper,
                "authority": "paper_store",
            },
            LENS_HISTORICAL_CLOSED: {
                "label": "Historical closed positions (unified archive)",
                "count": historical,
                "authority": "positions_unified_closed",
            },
            LENS_UNIFIED_STORE_OPEN: {
                "label": "Unified store open (diagnostic; not LIVE authority)",
                "count": unified_diag.get("open_live_count", 0),
                "paper_count": unified_diag.get("open_paper_count", 0),
                "authority": "positions_unified_db",
            },
        },
        # Convenience fields for Command Center / Guardrails contract.
        "live_open_count": live_total,
        "live_equity_count": live_equity_count,
        "live_option_count": live_option_count,
        "manual_open_count": len(manual),
        "paper_open_count": len(paper),
    }


def historicalize_orphan_unified_live_shares(
    *,
    dry_run: bool = True,
    confirm: bool = False,
    account_alias: str = "acct_individual",
) -> Dict[str, Any]:
    """Archive orphan live_shares_* rows vs fresh broker authority (not manual holdings).

    Defaults to dry_run=True. Destructive mutation requires confirm=True and a fresh,
    complete broker snapshot. Manual holdings are never used as proof a broker position
    is absent.
    """
    from datetime import datetime, timezone

    from app.core.portfolio.capital_authority_r70 import STATE_FRESH, get_capital_snapshot
    from app.core.portfolio.positions_unified_store_r279 import (
        INSTRUMENT_SHARES,
        _LOCK,
        _positions_db_path,
        init_db,
        rebuild_positions_unified,
    )

    cap = get_capital_snapshot(account_alias, allow_manual_fallback=False)
    broker_ready = cap.get("state") == STATE_FRESH and not cap.get("stale")
    completeness = str(cap.get("completeness") or "").lower()
    broker_complete = completeness in ("", "complete", "partial")  # refuse empty/missing only below

    refused_reason: Optional[str] = None
    if not broker_ready:
        refused_reason = (
            f"Broker authority not fresh for {account_alias} "
            f"(state={cap.get('state')}, as_of={cap.get('as_of')})"
        )
    else:
        from app.core.broker.snapshot_store import load_snapshot

        snap = load_snapshot(account_alias)
        if snap is None:
            refused_reason = "Broker snapshot missing"
            broker_ready = False
        elif getattr(snap, "completeness", None) in ("empty", "missing"):
            refused_reason = f"Broker snapshot incomplete ({snap.completeness})"
            broker_ready = False
            broker_complete = False

    broker_syms: set = set()
    if broker_ready:
        from app.core.portfolio.capital_authority_r70 import broker_share_quantities

        broker_syms = {s.upper() for s in broker_share_quantities(account_alias)}

    init_db()
    now = datetime.now(timezone.utc).isoformat()
    candidates: List[Dict[str, Any]] = []
    with _LOCK:
        import sqlite3

        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM positions_open WHERE is_paper = 0 AND instrument_type = ? AND id LIKE 'live_shares_%'",
                (INSTRUMENT_SHARES,),
            ).fetchall()
            for r in rows:
                sym = str(r["symbol"] or "").upper()
                rid = str(r["id"] or "")
                if not sym or not rid:
                    continue
                if broker_ready and sym in broker_syms:
                    continue
                # Only treat as orphan when we have fresh broker proof the symbol is absent.
                if not broker_ready:
                    continue
                candidates.append(
                    {
                        "id": rid,
                        "symbol": sym,
                        "qty": int(r["qty"] or 0),
                        "reason": "absent_from_fresh_broker_snapshot",
                    }
                )
        finally:
            conn.close()

    mutate = (not dry_run) and confirm and broker_ready and refused_reason is None
    if not dry_run and not confirm:
        return {
            "dry_run": False,
            "confirm": False,
            "refused": True,
            "refused_reason": "Destructive historicalize requires confirm=true",
            "orphan_live_shares_moved": 0,
            "candidates": candidates[:50],
            "candidate_count": len(candidates),
            "broker_state": cap.get("state"),
            "broker_as_of": cap.get("as_of"),
            "manual_only": True,
            "trade_execution": False,
        }
    if not dry_run and refused_reason:
        return {
            "dry_run": False,
            "confirm": confirm,
            "refused": True,
            "refused_reason": refused_reason,
            "orphan_live_shares_moved": 0,
            "candidates": candidates[:50],
            "candidate_count": len(candidates),
            "broker_state": cap.get("state"),
            "broker_as_of": cap.get("as_of"),
            "manual_only": True,
            "trade_execution": False,
        }

    moved: List[str] = []
    audit: List[Dict[str, Any]] = []
    if mutate:
        with _LOCK:
            import sqlite3

            conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("BEGIN")
                for c in candidates:
                    rid = c["id"]
                    sym = c["symbol"]
                    row = conn.execute(
                        "SELECT * FROM positions_open WHERE id = ?", (rid,)
                    ).fetchone()
                    if row is None:
                        continue
                    conn.execute(
                        """INSERT OR REPLACE INTO positions_closed (
                            id, symbol, instrument_type, is_paper, qty, avg_price, strike, expiry, right,
                            opened_ts, link_id, notes, tags, closed_ts, realized_pl, fees
                        ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"hist_{rid}",
                            sym,
                            INSTRUMENT_SHARES,
                            int(row["qty"] or 0),
                            row["avg_price"],
                            row["strike"],
                            row["expiry"],
                            row["right"],
                            (row["opened_ts"] or "")[:26],
                            row["link_id"],
                            "R70 historicalized orphan vs fresh broker (not LIVE)",
                            row["tags"],
                            now[:26],
                            None,
                            None,
                        ),
                    )
                    conn.execute("DELETE FROM positions_open WHERE id = ?", (rid,))
                    moved.append(rid)
                    audit.append({**c, "closed_id": f"hist_{rid}", "closed_ts": now})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    rebuild: Dict[str, Any] = {"skipped": True}
    if mutate:
        rebuild = rebuild_positions_unified(include_paper=True)
    return {
        "dry_run": dry_run or not mutate,
        "confirm": confirm,
        "refused": False,
        "orphan_live_shares_moved": len(moved),
        "sample_ids": moved[:10],
        "audit": audit[:50],
        "candidates": candidates[:50] if dry_run or not mutate else [],
        "candidate_count": len(candidates),
        "broker_symbols": sorted(broker_syms),
        "broker_state": cap.get("state"),
        "broker_as_of": cap.get("as_of"),
        "rebuild": rebuild,
        "manual_only": True,
        "trade_execution": False,
        "authority": "broker_snapshot",
    }


def unmirror_live_shares_open_by_symbol(symbol: str) -> int:
    """Remove live SHARES open rows for symbol from unified store (DELETE path)."""
    from app.core.portfolio.positions_unified_store_r279 import (
        INSTRUMENT_SHARES,
        _LOCK,
        _positions_db_path,
        init_db,
    )

    sym = (symbol or "").strip().upper()
    if not sym:
        return 0
    init_db()
    import sqlite3

    with _LOCK:
        conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
        try:
            cur = conn.execute(
                "DELETE FROM positions_open WHERE symbol = ? AND is_paper = 0 AND instrument_type = ?",
                (sym, INSTRUMENT_SHARES),
            )
            conn.commit()
            return int(cur.rowcount or 0)
        finally:
            conn.close()


def _manual_recovery_positions() -> List[Dict[str, Any]]:
    try:
        from app.core.accounts.holdings_db import _DEFAULT_ACCOUNT_ID, list_share_positions

        rows = list_share_positions(_DEFAULT_ACCOUNT_ID) or []
    except Exception:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("symbol") or "").upper()
        if not sym:
            continue
        out.append(
            {
                "symbol": sym,
                "quantity": r.get("quantity"),
                "average_cost": r.get("avg_cost"),
                "authority": "manual_holdings",
                "lens": LENS_MANUAL_RECOVERY,
            }
        )
    return out


def _paper_open_positions() -> List[Dict[str, Any]]:
    try:
        from app.core.paper import paper_store

        rows = []
        if hasattr(paper_store, "list_open_positions"):
            rows = paper_store.list_open_positions() or []
        elif hasattr(paper_store, "list_positions"):
            rows = [p for p in (paper_store.list_positions() or []) if str(p.get("status") or "").upper() == "OPEN"]
    except Exception:
        rows = []
    out: List[Dict[str, Any]] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "symbol": str(r.get("symbol") or "").upper(),
                "quantity": r.get("quantity") or r.get("qty"),
                "authority": "paper_store",
                "lens": LENS_PAPER_OPEN,
                "is_paper": True,
            }
        )
    return out


def _historical_closed_count() -> int:
    try:
        from app.core.portfolio.positions_unified_store_r279 import _LOCK, _positions_db_path, init_db
        import sqlite3

        init_db()
        with _LOCK:
            conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
            try:
                return int(conn.execute("SELECT COUNT(*) FROM positions_closed").fetchone()[0])
            finally:
                conn.close()
    except Exception:
        return 0


def _unified_open_diagnostic() -> Dict[str, int]:
    try:
        from app.core.portfolio.positions_unified_store_r279 import _LOCK, _positions_db_path, init_db
        import sqlite3

        init_db()
        with _LOCK:
            conn = sqlite3.connect(str(_positions_db_path()), check_same_thread=False)
            try:
                live = int(
                    conn.execute("SELECT COUNT(*) FROM positions_open WHERE is_paper = 0").fetchone()[0]
                )
                paper = int(
                    conn.execute("SELECT COUNT(*) FROM positions_open WHERE is_paper = 1").fetchone()[0]
                )
                return {"open_live_count": live, "open_paper_count": paper}
            finally:
                conn.close()
    except Exception:
        return {"open_live_count": 0, "open_paper_count": 0}
