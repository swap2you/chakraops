# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.3: wheel_state linked_position_ids retention (cap per symbol)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.wheel.state_store import (
    WHEEL_STATE_LINKED_POSITION_IDS_MAX,
    _apply_linked_position_retention,
    load_state,
    save_state_atomic,
)


@pytest.fixture
def tmp_wheel_state_path(tmp_path):
    path = tmp_path / "wheel_state.json"
    return path


def test_retention_trims_excess_linked_ids(tmp_wheel_state_path):
    """When linked_position_ids has more than max, trim to last N."""
    with patch("app.core.wheel.state_store._wheel_state_path", return_value=tmp_wheel_state_path):
        state = {
            "symbols": {
                "SPY": {
                    "state": "OPEN",
                    "last_updated_utc": "2026-02-25T12:00:00Z",
                    "linked_position_ids": [f"pos-{i}" for i in range(100)],
                },
            },
        }
        _apply_linked_position_retention(state)
        linked = state["symbols"]["SPY"]["linked_position_ids"]
        assert len(linked) <= WHEEL_STATE_LINKED_POSITION_IDS_MAX
        assert linked == [f"pos-{i}" for i in range(100 - WHEEL_STATE_LINKED_POSITION_IDS_MAX, 100)]


def test_retention_under_cap_unchanged(tmp_wheel_state_path):
    """When under cap, list unchanged."""
    with patch("app.core.wheel.state_store._wheel_state_path", return_value=tmp_wheel_state_path):
        state = {
            "symbols": {
                "NVDA": {
                    "state": "OPEN",
                    "linked_position_ids": ["pos-1", "pos-2"],
                },
            },
        }
        _apply_linked_position_retention(state)
        assert state["symbols"]["NVDA"]["linked_position_ids"] == ["pos-1", "pos-2"]


def test_save_state_applies_retention(tmp_wheel_state_path):
    """save_state_atomic trims linked_position_ids before writing."""
    with patch("app.core.wheel.state_store._wheel_state_path", return_value=tmp_wheel_state_path):
        state = {
            "symbols": {
                "QQQ": {
                    "state": "OPEN",
                    "last_updated_utc": "2026-02-25T12:00:00Z",
                    "linked_position_ids": [f"id-{i}" for i in range(80)],
                },
            },
        }
        save_state_atomic(state)
        raw = json.loads(tmp_wheel_state_path.read_text(encoding="utf-8"))
        linked = raw["symbols"]["QQQ"]["linked_position_ids"]
        assert len(linked) <= WHEEL_STATE_LINKED_POSITION_IDS_MAX
