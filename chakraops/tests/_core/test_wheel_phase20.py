# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 20.0: Manual wheel actions (assign/unassign/reset) and repair tests."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.wheel.actions_store import append_wheel_action, get_last_wheel_action_per_symbol
from app.core.wheel.state_machine import update_state_from_position_event
from app.core.wheel.state_store import load_state, clear_symbol_from_state
from app.core.wheel.repair import repair_wheel_state


@pytest.fixture
def tmp_wheel_state(tmp_path):
    path = tmp_path / "wheel_state.json"
    path.write_text(json.dumps({"symbols": {}}), encoding="utf-8")
    def _path():
        return path
    with patch("app.core.wheel.state_store._wheel_state_path", side_effect=_path):
        yield tmp_path


@pytest.fixture
def tmp_wheel_actions(tmp_path):
    path = tmp_path / "wheel_actions.jsonl"
    path.write_text("", encoding="utf-8")
    with patch("app.core.wheel.actions_store._wheel_actions_path", return_value=path):
        yield path


def test_manual_assign_updates_state(tmp_wheel_state, tmp_wheel_actions):
    """Assign appends action and sets state to ASSIGNED."""
    sym = "SPY"
    append_wheel_action(sym, "ASSIGNED")
    update_state_from_position_event(sym, "ASSIGNED", "")
    data = load_state()
    entry = data["symbols"].get(sym)
    assert entry is not None
    assert entry["state"] == "ASSIGNED"
    last = get_last_wheel_action_per_symbol()
    assert last.get(sym, {}).get("action") == "ASSIGNED"


def test_manual_unassign_after_assign(tmp_wheel_state, tmp_wheel_actions):
    """Unassign after assign sets state to EMPTY and clears linked_position_ids."""
    sym = "SPY"
    append_wheel_action(sym, "ASSIGNED")
    update_state_from_position_event(sym, "ASSIGNED", "")
    append_wheel_action(sym, "UNASSIGNED")
    update_state_from_position_event(sym, "UNASSIGNED", "")
    data = load_state()
    entry = data["symbols"].get(sym)
    assert entry is not None
    assert entry["state"] == "EMPTY"
    assert (entry.get("linked_position_ids") or []) == []


def test_reset_clears_symbol_from_state(tmp_wheel_state, tmp_wheel_actions):
    """Reset clears symbol from wheel_state (entry removed)."""
    sym = "SPY"
    append_wheel_action(sym, "ASSIGNED")
    update_state_from_position_event(sym, "ASSIGNED", "")
    append_wheel_action(sym, "RESET")
    clear_symbol_from_state(sym)
    data = load_state()
    assert sym not in (data.get("symbols") or {})


def test_repair_rebuilds_state_from_open_positions(tmp_wheel_state, tmp_wheel_actions):
    """Repair builds wheel_state from open positions list; state matches positions."""
    # Create mock open positions (need position_id and symbol)
    class MockPos:
        def __init__(self, symbol: str, position_id: str, status: str = "OPEN"):
            self.symbol = symbol
            self.position_id = position_id
            self.status = status

    open_positions = [
        MockPos("SPY", "pos-spy-1"),
        MockPos("QQQ", "pos-qqq-1"),
    ]
    result = repair_wheel_state(open_positions)
    assert result["status"] == "OK"
    data = load_state()
    symbols = data.get("symbols") or {}
    assert "SPY" in symbols
    assert symbols["SPY"]["state"] == "OPEN"
    assert symbols["SPY"]["linked_position_ids"] == ["pos-spy-1"]
    assert "QQQ" in symbols
    assert symbols["QQQ"]["state"] == "OPEN"
    assert symbols["QQQ"]["linked_position_ids"] == ["pos-qqq-1"]
    assert "SPY" in result["repaired_symbols"] or "QQQ" in result["repaired_symbols"]
