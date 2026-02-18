# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 18.0: Wheel state machine — update state from position events and manual overrides."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.core.wheel.state_store import WHEEL_STATES, load_state, save_state_atomic

logger = logging.getLogger(__name__)

EVENT_TYPES = frozenset({"OPEN", "CLOSE", "ASSIGNED", "UNASSIGNED", "ROLL"})


def update_state_from_position_event(
    symbol: str,
    event_type: str,
    position_id: str,
    payload: Dict[str, Any] | None = None,
) -> str:
    """
    Update wheel state for symbol based on position event.
    event_type: OPEN | CLOSE | ASSIGNED | UNASSIGNED | ROLL
    Returns new state for the symbol.
    """
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {EVENT_TYPES}")
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol required")

    state_data = load_state()
    symbols = state_data.setdefault("symbols", {})
    entry = symbols.get(symbol) or {
        "state": "EMPTY",
        "last_updated_utc": None,
        "linked_position_ids": [],
    }
    linked = list(entry.get("linked_position_ids") or [])
    now = datetime.now(timezone.utc).isoformat()

    if event_type == "OPEN":
        if position_id and position_id not in linked:
            linked.append(position_id)
        entry["state"] = "OPEN"
        entry["linked_position_ids"] = linked
    elif event_type == "CLOSE":
        if position_id and position_id in linked:
            linked.remove(position_id)
        entry["linked_position_ids"] = linked
        entry["state"] = "OPEN" if linked else "CLOSED"
    elif event_type == "ROLL":
        # ROLL = close old + open new. Caller typically sends OPEN for new; old gets CLOSE.
        # If we get ROLL, treat as OPEN for the new position (payload may have new position_id)
        new_id = (payload or {}).get("new_position_id") or position_id
        if position_id in linked:
            linked.remove(position_id)
        if new_id and new_id not in linked:
            linked.append(new_id)
        entry["linked_position_ids"] = linked
        entry["state"] = "OPEN" if linked else "CLOSED"
    elif event_type == "ASSIGNED":
        entry["state"] = "ASSIGNED"
        entry["linked_position_ids"] = linked
    elif event_type == "UNASSIGNED":
        entry["state"] = "EMPTY"
        entry["linked_position_ids"] = []
    entry["last_updated_utc"] = now
    symbols[symbol] = entry
    save_state_atomic(state_data)
    return entry["state"]
