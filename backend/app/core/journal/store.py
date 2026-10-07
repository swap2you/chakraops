# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Trade Journal persistence: file-based store under out/trades/."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.journal.models import Trade, Fill, FillAction, generate_trade_id, generate_fill_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _get_journal_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "trades"


def _ensure_journal_dir() -> Path:
    p = _get_journal_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _trade_path(trade_id: str) -> Path:
    return _ensure_journal_dir() / f"{trade_id}.json"


_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# PnL and derived fields
# ---------------------------------------------------------------------------


def compute_trade_derived(trade: Trade) -> Trade:
    """
    Compute remaining_qty, avg_entry, avg_exit, realized_pnl from fills.
    
    - OPEN fills add to position; CLOSE fills reduce and contribute to realized.
    - remaining_qty = contracts (from trade) + sum(OPEN qty) - sum(CLOSE qty)
    - avg_entry: vwap of OPEN fills (or entry_mid_est if no OPEN fills)
    - avg_exit: vwap of CLOSE fills
    - realized_pnl: for each CLOSE fill, (exit_price - avg_entry) * qty * multiplier - fees
      CSP multiplier = 100 per contract.
    """
    contracts = trade.contracts
    open_qty = sum(f.qty for f in trade.fills if f.action == FillAction.OPEN)
    close_qty = sum(f.qty for f in trade.fills if f.action == FillAction.CLOSE)
    
    # Remaining = initial + opens - closes (initial is "contracts" at trade level)
    trade.remaining_qty = contracts + open_qty - close_qty
    
    # Avg entry: from OPEN fills or use entry_mid_est
    open_fills = [f for f in trade.fills if f.action == FillAction.OPEN]
    if open_fills:
        total = sum(f.price * f.qty for f in open_fills)
        total_qty = sum(f.qty for f in open_fills)
        trade.avg_entry = total / total_qty if total_qty else trade.entry_mid_est
    else:
        trade.avg_entry = trade.entry_mid_est
    
    # Avg exit: from CLOSE fills
    close_fills = [f for f in trade.fills if f.action == FillAction.CLOSE]
    if close_fills:
        total = sum(f.price * f.qty for f in close_fills)
        total_qty = sum(f.qty for f in close_fills)
        trade.avg_exit = total / total_qty if total_qty else None
    else:
        trade.avg_exit = None
    
    # Realized PnL: (exit - entry) * qty * 100 - fees (for options)
    # TODO Phase 11: Integrate fee model (per-contract, assignment fees) and auction logic.
    # Entry side: we sold premium, so entry is credit. Close we buy back.
    # Realized = credit received at open - debit at close - fees = (entry - exit) * 100 * qty - fees
    multiplier = 100  # per contract for options
    realized = 0.0
    entry_for_pnl = trade.avg_entry or 0.0
    
    for f in trade.fills:
        if f.action == FillAction.CLOSE:
            # We sold at avg_entry, bought back at f.price -> profit = (entry - exit) * 100 * qty
            realized += (entry_for_pnl - f.price) * f.qty * multiplier - f.fees
        elif f.action == FillAction.OPEN:
            # Opening add: no realized yet; fees reduce PnL when we close
            pass
    
    trade.realized_pnl = round(realized, 2) if close_fills else None
    return trade


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_trades(limit: int = 100) -> List[Trade]:
    """List trades, newest first."""
    journal_dir = _get_journal_dir()
    if not journal_dir.exists():
        return []
    
    trades = []
    files = sorted(
        [f for f in journal_dir.glob("trade_*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]
    
    with _LOCK:
        for path in files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                t = Trade.from_dict(data)
                compute_trade_derived(t)
                trades.append(t)
            except Exception as e:
                logger.warning("[JOURNAL] Failed to load %s: %s", path, e)
    
    return trades


def get_trade(trade_id: str) -> Optional[Trade]:
    """Get a single trade by ID."""
    path = _trade_path(trade_id)
    if not path.exists():
        return None
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            t = Trade.from_dict(data)
            compute_trade_derived(t)
            return t
        except Exception as e:
            logger.warning("[JOURNAL] Failed to load %s: %s", path, e)
            return None


def create_trade(payload: Dict[str, Any]) -> Trade:
    """Create a new trade. trade_id can be provided or generated."""
    trade_id = payload.get("trade_id") or generate_trade_id()
    payload["trade_id"] = trade_id
    payload.setdefault("fills", [])
    t = Trade.from_dict(payload)
    compute_trade_derived(t)
    path = _trade_path(trade_id)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(t.to_dict(), f, indent=2, default=str)
    logger.info("[JOURNAL] Created trade %s", trade_id)
    return t


def update_trade(trade_id: str, payload: Dict[str, Any]) -> Optional[Trade]:
    """Update an existing trade. Merges with existing; fills can be replaced if provided."""
    existing = get_trade(trade_id)
    if not existing:
        return None
    
    d = existing.to_dict()
    # Merge: only update keys present in payload (except trade_id and fills)
    for key in ("symbol", "strategy", "opened_at", "expiry", "strike", "side", "contracts",
                "entry_mid_est", "run_id", "notes", "stop_level", "target_levels"):
        if key in payload:
            d[key] = payload[key]
    if "fills" in payload:
        d["fills"] = payload["fills"]
    
    d["trade_id"] = trade_id
    t = Trade.from_dict(d)
    compute_trade_derived(t)
    path = _trade_path(trade_id)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(t.to_dict(), f, indent=2, default=str)
    logger.info("[JOURNAL] Updated trade %s", trade_id)
    return t


def delete_trade(trade_id: str) -> bool:
    """Delete a trade and its file."""
    path = _trade_path(trade_id)
    if not path.exists():
        return False
    with _LOCK:
        path.unlink()
    logger.info("[JOURNAL] Deleted trade %s", trade_id)
    return True


def add_fill(trade_id: str, payload: Dict[str, Any]) -> Optional[Trade]:
    """Add a fill to a trade. Payload: filled_at, action, qty, price, fees?, tags?"""
    trade = get_trade(trade_id)
    if not trade:
        return None
    
    fill_id = payload.get("fill_id") or generate_fill_id()
    fill = Fill(
        fill_id=fill_id,
        trade_id=trade_id,
        filled_at=payload["filled_at"],
        action=FillAction(payload.get("action", "CLOSE")),
        qty=int(payload["qty"]),
        price=float(payload["price"]),
        fees=float(payload.get("fees", 0)),
        tags=list(payload.get("tags", [])),
    )
    trade.fills.append(fill)
    compute_trade_derived(trade)
    path = _trade_path(trade_id)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trade.to_dict(), f, indent=2, default=str)
    logger.info("[JOURNAL] Added fill %s to trade %s", fill_id, trade_id)
    return trade


def delete_fill(trade_id: str, fill_id: str) -> Optional[Trade]:
    """Remove a fill from a trade."""
    trade = get_trade(trade_id)
    if not trade:
        return None
    
    trade.fills = [f for f in trade.fills if f.fill_id != fill_id]
    compute_trade_derived(trade)
    path = _trade_path(trade_id)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(trade.to_dict(), f, indent=2, default=str)
    logger.info("[JOURNAL] Deleted fill %s from trade %s", fill_id, trade_id)
    return trade


# ---------------------------------------------------------------------------
# Next actions (from exit-rules engine, written by nightly)
# ---------------------------------------------------------------------------


def _next_actions_path() -> Path:
    return _get_journal_dir() / "next_actions.json"


def get_next_actions() -> Dict[str, Dict[str, Any]]:
    """Load trade_id -> { action, severity, message, rule_code?, evaluated_at } from next_actions.json."""
    path = _next_actions_path()
    if not path.exists():
        return {}
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("[JOURNAL] Failed to load next_actions: %s", e)
            return {}


def save_next_actions(next_actions: Dict[str, Dict[str, Any]]) -> None:
    """Write next_actions.json. Called by nightly after evaluating exit rules."""
    path = _next_actions_path()
    _ensure_journal_dir()
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(next_actions, f, indent=2, default=str)
    logger.info("[JOURNAL] Saved next_actions for %d trades", len(next_actions))
