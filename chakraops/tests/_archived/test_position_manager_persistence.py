# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 6.7: position manager persistence APIs (create_manual_position, update_notes, record_partial_close, record_close, record_assignment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.persistence import (
    add_capital_ledger_entry,
    add_position_event,
    create_manual_position,
    get_capital_ledger_entries,
    get_position_by_id,
    get_position_history,
    get_positions_for_view,
    init_persistence_db,
    record_assignment,
    record_close,
    record_partial_close,
    update_position_notes,
)
from app.core.position_lifecycle import InvalidLifecycleTransitionError


@pytest.fixture
def temp_db():
    """Use a temporary database so tests don't touch shared DB."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    try:
        from app.db import database
        from app.core import persistence
        orig_db = database.get_db_path
        database.get_db_path = lambda: db_path
        persistence.get_db_path = lambda: db_path
        init_persistence_db()
        yield db_path
    finally:
        database.get_db_path = orig_db
        persistence.get_db_path = orig_db
        if db_path.exists():
            db_path.unlink(missing_ok=True)


def test_create_manual_position_creates_open_position_and_ledger(temp_db):
    """create_manual_position creates OPEN position + OPENED event + ledger OPEN."""
    pos = create_manual_position(
        symbol="AAPL",
        strategy_type="CSP",
        expiry="2026-03-20",
        strike=150.0,
        contracts=1,
        entry_credit=250.0,
        open_date="2026-02-01",
        notes="manual test",
    )
    assert pos.id
    assert pos.symbol == "AAPL"
    assert pos.lifecycle_state == "OPEN"
    assert pos.entry_credit == 250.0
    assert pos.open_date == "2026-02-01"
    assert pos.notes == "manual test"

    history = get_position_history(pos.id)
    assert len(history) == 1
    assert history[0]["event_type"] == "OPENED"

    entries = get_capital_ledger_entries(position_id=pos.id)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "OPEN"
    assert entries[0]["cash_delta"] == 250.0


def test_create_manual_position_shares(temp_db):
    """create_manual_position with strategy_type SHARES creates position with entry_credit and open_date."""
    pos = create_manual_position(
        symbol="SPY",
        strategy_type="SHARES",
        expiry=None,
        strike=None,
        contracts=100,
        entry_credit=0.0,
        open_date="2026-02-01",
        notes="shares test",
    )
    assert pos.symbol == "SPY"
    assert pos.position_type == "SHARES"
    assert pos.lifecycle_state == "OPEN"
    assert pos.open_date == "2026-02-01"
    entries = get_capital_ledger_entries(position_id=pos.id)
    assert len(entries) == 1
    assert entries[0]["event_type"] == "OPEN"


def test_update_position_notes_writes_notes_and_manual_note_event(temp_db):
    """update_position_notes writes notes and MANUAL_NOTE event."""
    pos = create_manual_position(
        symbol="MSFT",
        strategy_type="CSP",
        expiry="2026-04-18",
        strike=400.0,
        contracts=1,
        entry_credit=300.0,
        open_date="2026-02-01",
        notes="initial",
    )
    update_position_notes(pos.id, "updated note text")
    reloaded = get_position_by_id(pos.id)
    assert reloaded is not None
    assert reloaded.notes == "updated note text"
    history = get_position_history(pos.id)
    event_types = [e["event_type"] for e in history]
    assert "OPENED" in event_types
    assert "MANUAL_NOTE" in event_types


def test_record_partial_close_updates_lifecycle_ledger_event(temp_db):
    """record_partial_close updates lifecycle to PARTIALLY_CLOSED, adds ledger PARTIAL_CLOSE, adds TARGET_1_HIT event."""
    pos = create_manual_position(
        symbol="NVDA",
        strategy_type="CSP",
        expiry="2026-05-15",
        strike=800.0,
        contracts=1,
        entry_credit=500.0,
        open_date="2026-02-01",
    )
    record_partial_close(pos.id, 100.0, notes="partial 1")
    reloaded = get_position_by_id(pos.id)
    assert reloaded is not None
    assert reloaded.lifecycle_state == "PARTIALLY_CLOSED"
    assert reloaded.realized_pnl == 100.0

    entries = get_capital_ledger_entries(position_id=pos.id)
    types = [e["event_type"] for e in entries]
    assert "OPEN" in types
    assert "PARTIAL_CLOSE" in types
    assert any(e["event_type"] == "PARTIAL_CLOSE" and e["cash_delta"] == 100.0 for e in entries)

    history = get_position_history(pos.id)
    assert any(e["event_type"] == "TARGET_1_HIT" for e in history)


def test_record_close_moves_to_closed_sets_close_date_ledger_event(temp_db):
    """record_close moves to CLOSED, adds ledger CLOSE, sets close_date, adds CLOSED event."""
    pos = create_manual_position(
        symbol="GOOGL",
        strategy_type="CSP",
        expiry="2026-06-20",
        strike=160.0,
        contracts=1,
        entry_credit=200.0,
        open_date="2026-02-01",
    )
    record_close(pos.id, 50.0, notes="closed")
    reloaded = get_position_by_id(pos.id)
    assert reloaded is not None
    assert reloaded.lifecycle_state == "CLOSED"
    assert reloaded.close_date is not None
    assert reloaded.realized_pnl == 50.0

    entries = get_capital_ledger_entries(position_id=pos.id)
    assert any(e["event_type"] == "CLOSE" and e["cash_delta"] == 50.0 for e in entries)
    history = get_position_history(pos.id)
    assert any(e["event_type"] == "CLOSED" for e in history)


def test_record_assignment_moves_to_assigned_ledger_event(temp_db):
    """record_assignment moves to ASSIGNED, adds ASSIGNED event, adds ledger ASSIGNMENT 0.0."""
    pos = create_manual_position(
        symbol="META",
        strategy_type="CSP",
        expiry="2026-03-21",
        strike=500.0,
        contracts=1,
        entry_credit=400.0,
        open_date="2026-02-01",
    )
    record_assignment(pos.id, notes="assigned")
    reloaded = get_position_by_id(pos.id)
    assert reloaded is not None
    assert reloaded.lifecycle_state == "ASSIGNED"

    entries = get_capital_ledger_entries(position_id=pos.id)
    assert any(e["event_type"] == "ASSIGNMENT" and e["cash_delta"] == 0.0 for e in entries)
    history = get_position_history(pos.id)
    assert any(e["event_type"] == "ASSIGNED" for e in history)


def test_invalid_lifecycle_transitions_raise(temp_db):
    """Invalid lifecycle transitions raise InvalidLifecycleTransitionError (e.g. record_assignment on CLOSED position)."""
    pos = create_manual_position(
        symbol="AMZN",
        strategy_type="CSP",
        expiry="2026-04-18",
        strike=180.0,
        contracts=1,
        entry_credit=220.0,
        open_date="2026-02-01",
    )
    record_close(pos.id, 20.0)
    reloaded = get_position_by_id(pos.id)
    assert reloaded is not None
    assert reloaded.lifecycle_state == "CLOSED"
    # CLOSED -> ASSIGNED is invalid; record_assignment must raise
    with pytest.raises(InvalidLifecycleTransitionError):
        record_assignment(pos.id)


def test_get_position_by_id_returns_none_for_missing():
    """get_position_by_id returns None for non-existent id."""
    init_persistence_db()
    out = get_position_by_id("nonexistent-id-xyz")
    assert out is None


def test_update_position_notes_raises_for_missing(temp_db):
    """update_position_notes raises ValueError for missing position."""
    with pytest.raises(ValueError, match="not found"):
        update_position_notes("nonexistent-id-xyz", "notes")
