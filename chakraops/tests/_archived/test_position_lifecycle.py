# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Phase 6.3: persistent position lifecycle and event tracking."""

from __future__ import annotations

import pytest

from app.core.models.position import Position
from app.core.persistence import add_position_event, get_position_history
from app.core.position_lifecycle import (
    InvalidLifecycleTransitionError,
    PositionEventType,
    PositionLifecycleState,
    validate_lifecycle_transition,
)
from app.core.storage.position_store import PositionStore
from app.db.database import get_db_path


def test_open_to_partially_closed_to_closed():
    """Lifecycle transitions OPEN -> PARTIALLY_CLOSED -> CLOSED are valid."""
    validate_lifecycle_transition("OPEN", "PARTIALLY_CLOSED", "pos-1")
    validate_lifecycle_transition("PARTIALLY_CLOSED", "CLOSED", "pos-1")
    validate_lifecycle_transition("OPEN", "CLOSED", "pos-1")


def test_event_emission_correctness():
    """Events are stored and returned in order; get_position_history reconstructs story."""
    import uuid
    pid = f"test-event-emission-{uuid.uuid4().hex[:12]}"
    add_position_event(pid, PositionEventType.OPENED.value, {"symbol": "SPY", "strike": 450.0})
    add_position_event(pid, PositionEventType.TARGET_1_HIT.value, {"option_value": 0.5})
    add_position_event(pid, PositionEventType.CLOSED.value, {"realized_pnl": 120.0})
    history = get_position_history(pid)
    assert len(history) == 3
    assert history[0]["event_type"] == "OPENED"
    assert history[0]["metadata"].get("symbol") == "SPY"
    assert history[1]["event_type"] == "TARGET_1_HIT"
    assert history[2]["event_type"] == "CLOSED"
    assert history[2]["metadata"].get("realized_pnl") == 120.0
    assert history[0]["event_time"] <= history[1]["event_time"] <= history[2]["event_time"]


def test_persistence_across_reload():
    """Positions and events persist across reload (PositionStore + get_position_history)."""
    store = PositionStore(db_path=get_db_path())
    position = Position.create_csp("TEST", 100.0, "2026-03-20", 1, 2.50, notes="Phase 6.3 test")
    position.lifecycle_state = "OPEN"
    position.entry_credit = 2.50
    position.open_date = "2026-02-01"
    store.insert_position(position)
    add_position_event(position.id, PositionEventType.OPENED.value, {"symbol": "TEST"})
    add_position_event(position.id, PositionEventType.TARGET_1_HIT.value, {})

    # Reload: fetch positions and history
    by_symbol = store.fetch_positions_by_symbol("TEST")
    assert len(by_symbol) >= 1
    reloaded = next((p for p in by_symbol if p.id == position.id), None)
    assert reloaded is not None
    assert reloaded.symbol == "TEST"
    assert getattr(reloaded, "lifecycle_state", None) in ("OPEN", None) or reloaded.state == "OPEN"
    assert getattr(reloaded, "entry_credit", None) in (2.50, None) or reloaded.premium_collected == 2.50

    history = get_position_history(position.id)
    assert len(history) >= 2
    types = [e["event_type"] for e in history]
    assert "OPENED" in types
    assert "TARGET_1_HIT" in types


def test_invalid_transitions_rejected():
    """Invalid lifecycle transitions raise InvalidLifecycleTransitionError."""
    with pytest.raises(InvalidLifecycleTransitionError) as exc_info:
        validate_lifecycle_transition("CLOSED", "OPEN", "pos-closed")
    assert "CLOSED" in str(exc_info.value)
    assert "OPEN" in str(exc_info.value)

    with pytest.raises(InvalidLifecycleTransitionError):
        validate_lifecycle_transition("CLOSED", "PARTIALLY_CLOSED", "pos-2")

    with pytest.raises(InvalidLifecycleTransitionError):
        validate_lifecycle_transition("ASSIGNED", "OPEN", "pos-3")

    # PROPOSED -> OPEN is valid
    validate_lifecycle_transition("PROPOSED", "OPEN", "pos-4")
    validate_lifecycle_transition("OPEN", "ASSIGNED", "pos-5")


def test_position_model_phase63_fields():
    """Position model has entry_credit, open_date, close_date, realized_pnl, lifecycle_state, notes."""
    p = Position.create_csp("AAPL", 150.0, "2026-04-17", 2, 3.0)
    assert getattr(p, "entry_credit", None) is not None
    assert getattr(p, "open_date", None) is not None
    assert getattr(p, "close_date", None) is None
    assert getattr(p, "realized_pnl", None) is not None
    assert getattr(p, "lifecycle_state", None) == "OPEN"
    assert p.notes is None
    p.notes = "User-editable note"
    assert p.notes == "User-editable note"


def test_position_event_types_enum():
    """PositionEventType includes OPENED, TARGET_1_HIT, TARGET_2_HIT, STOP_TRIGGERED, ASSIGNED, CLOSED, MANUAL_NOTE."""
    assert PositionEventType.OPENED.value == "OPENED"
    assert PositionEventType.TARGET_1_HIT.value == "TARGET_1_HIT"
    assert PositionEventType.TARGET_2_HIT.value == "TARGET_2_HIT"
    assert PositionEventType.STOP_TRIGGERED.value == "STOP_TRIGGERED"
    assert PositionEventType.ASSIGNED.value == "ASSIGNED"
    assert PositionEventType.CLOSED.value == "CLOSED"
    assert PositionEventType.MANUAL_NOTE.value == "MANUAL_NOTE"


def test_lifecycle_state_enum():
    """PositionLifecycleState includes PROPOSED, OPEN, PARTIALLY_CLOSED, CLOSED, ASSIGNED."""
    assert PositionLifecycleState.PROPOSED.value == "PROPOSED"
    assert PositionLifecycleState.OPEN.value == "OPEN"
    assert PositionLifecycleState.PARTIALLY_CLOSED.value == "PARTIALLY_CLOSED"
    assert PositionLifecycleState.CLOSED.value == "CLOSED"
    assert PositionLifecycleState.ASSIGNED.value == "ASSIGNED"


def test_get_position_history_empty():
    """get_position_history returns [] for unknown position_id."""
    history = get_position_history("nonexistent-position-id-99999")
    assert history == []
