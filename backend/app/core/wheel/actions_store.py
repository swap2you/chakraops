# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 20.0: Wheel manual actions — append-only audit (assign, unassign, reset)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_RETENTION_LINES = 5000

WHEEL_ACTIONS = frozenset({"ASSIGNED", "UNASSIGNED", "RESET"})


def _wheel_actions_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "wheel_actions.jsonl"


def _prune_if_needed(path: Path) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) <= _RETENTION_LINES:
        return
    kept = lines[-_RETENTION_LINES:]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="wheel_actions.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in kept:
                f.write(ln + "\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def append_wheel_action(symbol: str, action: str, position_id: Optional[str] = None) -> None:
    """Append a wheel action (ASSIGNED, UNASSIGNED, RESET)."""
    if action not in WHEEL_ACTIONS:
        raise ValueError(f"action must be one of {WHEEL_ACTIONS}")
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol required")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    record: Dict[str, Any] = {
        "symbol": symbol,
        "action": action,
        "at_utc": now,
    }
    if position_id:
        record["position_id"] = position_id
    path = _wheel_actions_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        from app.core.io.locks import with_file_lock
        with with_file_lock(path, timeout_ms=2000):
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            _prune_if_needed(path)
    logger.info("[WHEEL_ACTIONS] %s %s", symbol, action)


def get_last_wheel_action_per_symbol() -> Dict[str, Dict[str, Any]]:
    """Return {symbol: {action, at_utc}} for the most recent action per symbol."""
    path = _wheel_actions_path()
    if not path.exists():
        return {}
    by_symbol: Dict[str, Dict[str, Any]] = {}
    with _LOCK:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    sym = (rec.get("symbol") or "").strip().upper()
                    if sym:
                        by_symbol[sym] = {"action": rec.get("action"), "at_utc": rec.get("at_utc")}
                except json.JSONDecodeError:
                    pass
    return by_symbol


def load_wheel_actions_for_repair(limit_per_symbol: int = 50) -> Dict[str, List[Dict[str, Any]]]:
    """Load recent wheel actions grouped by symbol (newest last per symbol) for repair logic."""
    path = _wheel_actions_path()
    if not path.exists():
        return {}
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    with _LOCK:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    sym = (rec.get("symbol") or "").strip().upper()
                    if sym:
                        by_symbol.setdefault(sym, []).append(rec)
                except json.JSONDecodeError:
                    pass
    for sym in by_symbol:
        by_symbol[sym] = by_symbol[sym][-limit_per_symbol:]
    return by_symbol
