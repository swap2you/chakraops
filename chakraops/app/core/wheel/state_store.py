# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 18.0: Wheel state store - atomic load/save of per-symbol wheel state."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

WHEEL_STATES = frozenset({"EMPTY", "ASSIGNED", "OPEN", "CLOSED"})


def _wheel_state_path() -> Path:
    try:
        from app.core.eval.evaluation_store_v2 import get_decision_store_path
        out = get_decision_store_path().parent
    except Exception:
        out = Path(__file__).resolve().parents[3] / "out"
    out.mkdir(parents=True, exist_ok=True)
    return out / "wheel_state.json"


def load_state() -> Dict[str, Any]:
    """Load wheel state. Returns {symbols: {symbol: {state, last_updated_utc, linked_position_ids[]}}}."""
    path = _wheel_state_path()
    if not path.exists():
        return {"symbols": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        symbols = data.get("symbols") or {}
        for sym, ent in list(symbols.items()):
            if not isinstance(ent, dict):
                symbols[sym] = {"state": "EMPTY", "last_updated_utc": None, "linked_position_ids": []}
            elif "linked_position_ids" not in ent:
                ent["linked_position_ids"] = []
        return {"symbols": symbols}
    except Exception as e:
        logger.warning("[WHEEL] Failed to load state: %s", e)
        return {"symbols": {}}


def save_state_atomic(state: Dict[str, Any]) -> None:
    """Save wheel state atomically via atomic_write_json."""
    from app.core.io.atomic import atomic_write_json
    path = _wheel_state_path()
    atomic_write_json(path, state, indent=2)
