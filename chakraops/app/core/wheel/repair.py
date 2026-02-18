# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 20.0: Rebuild wheel_state from open positions (primary) and wheel actions (secondary)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from app.core.wheel.state_store import load_state, save_state_atomic
from app.core.wheel.actions_store import load_wheel_actions_for_repair


def repair_wheel_state(open_positions: List[Any]) -> Dict[str, Any]:
    """
    Rebuild wheel_state.json from open positions list (primary) and recent wheel actions (secondary).
    - For each symbol with open position(s): state=OPEN, linked_position_ids = list of position_ids.
    - For symbols that had ASSIGNED/UNASSIGNED/RESET in wheel_actions but no open position: state from last action (ASSIGNED or EMPTY).
    - Removed symbols: in old state but no open position and no recent manual action (or last action was RESET/UNASSIGNED).
    Returns {repaired_symbols: [str], removed_symbols: [str], status: str}.
    """
    now = datetime.now(timezone.utc).isoformat()
    open_by_symbol: Dict[str, List[Any]] = {}
    for p in open_positions:
        sym = (getattr(p, "symbol", "") or "").strip().upper()
        if not sym:
            continue
        if (getattr(p, "status", "") or "").upper() not in ("OPEN", "PARTIAL_EXIT"):
            continue
        open_by_symbol.setdefault(sym, []).append(p)

    actions_by_symbol = load_wheel_actions_for_repair(limit_per_symbol=20)
    old_state = load_state()
    old_symbols = old_state.get("symbols") or {}
    new_symbols: Dict[str, Dict[str, Any]] = {}
    repaired: List[str] = []
    removed: List[str] = []

    for sym, positions in open_by_symbol.items():
        linked = [getattr(p, "position_id", "") or "" for p in positions if getattr(p, "position_id", None)]
        linked = [x for x in linked if x]
        new_symbols[sym] = {
            "state": "OPEN",
            "last_updated_utc": now,
            "linked_position_ids": linked,
        }
        old_entry = old_symbols.get(sym)
        if not old_entry or old_entry.get("linked_position_ids") != linked or (old_entry.get("state") or "") != "OPEN":
            repaired.append(sym)

    for sym, action_list in actions_by_symbol.items():
        if sym in new_symbols:
            continue
        if not action_list:
            continue
        last = action_list[-1]
        act = (last.get("action") or "").upper()
        if act == "ASSIGNED":
            new_symbols[sym] = {
                "state": "ASSIGNED",
                "last_updated_utc": last.get("at_utc") or now,
                "linked_position_ids": [],
            }
            repaired.append(sym)
        elif act in ("UNASSIGNED", "RESET"):
            if sym in old_symbols:
                removed.append(sym)

    for sym in old_symbols:
        if sym not in new_symbols:
            removed.append(sym)

    new_state = {"symbols": new_symbols}
    save_state_atomic(new_state)
    return {
        "repaired_symbols": list(dict.fromkeys(repaired)),
        "removed_symbols": list(dict.fromkeys(removed)),
        "status": "OK",
    }
