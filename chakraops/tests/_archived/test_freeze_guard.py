# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for Phase 6.1: run mode and config freeze guard."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.core.freeze_guard import (
    FreezeResult,
    build_critical_config_snapshot,
    check_freeze,
    hash_snapshot,
    record_run,
)
from app.core.run_mode import RunMode


def test_dry_run_ignores_freeze():
    """Dry-run always allowed; config freeze not enforced."""
    result = check_freeze(RunMode.DRY_RUN)
    assert result.allowed is True
    assert result.config_frozen is False
    assert "DRY_RUN" in result.message
    assert result.changed_keys == []


def test_first_run_allowed_paper_live():
    """First run (no previous state) with PAPER_LIVE is allowed and config_frozen=True."""
    with patch("app.core.freeze_guard.get_config_freeze_state", return_value=None):
        result = check_freeze(RunMode.PAPER_LIVE)
    assert result.allowed is True
    assert result.config_frozen is True
    assert "First run" in result.message or "frozen" in result.message.lower()


def test_freeze_violation_blocks_execution():
    """When run_mode != DRY_RUN and config hash changed, execution is blocked and changed keys reported."""
    snapshot = build_critical_config_snapshot()
    current_hash = hash_snapshot(snapshot)
    # Simulate previous run with different config (different hash)
    fake_previous = dict(snapshot)
    fake_previous["volatility"] = {"vix_threshold": 999.0, "vix_change_pct": 20.0, "range_multiplier": 2.0}
    previous_json = json.dumps(fake_previous, sort_keys=True, separators=(",", ":"))
    fake_state = {
        "config_hash": "different_hash_than_current",
        "config_snapshot": previous_json,
        "run_mode": "PAPER_LIVE",
        "updated_at": "2026-01-31T12:00:00Z",
    }
    with patch("app.core.freeze_guard.get_config_freeze_state", return_value=fake_state):
        result = check_freeze(RunMode.PAPER_LIVE)
    assert result.allowed is False
    assert result.config_frozen is False
    assert "Config changed" in result.message or "blocked" in result.message.lower()
    assert "volatility" in result.changed_keys


def test_snapshot_shows_run_mode_and_freeze_status():
    """Snapshot (critical config) is deterministic; hash_snapshot and run_mode/freeze status are consistent."""
    snapshot = build_critical_config_snapshot()
    assert "volatility" in snapshot
    assert "confidence" in snapshot
    assert "portfolio" in snapshot
    assert "environment" in snapshot
    assert "options_context" in snapshot
    assert "scoring" in snapshot
    assert "context_gate" in snapshot
    assert "selection" in snapshot
    h = hash_snapshot(snapshot)
    assert isinstance(h, str)
    assert len(h) == 64  # sha256 hex
    # Same snapshot -> same hash
    assert hash_snapshot(snapshot) == h
    # Result for LIVE with no prior state: allowed, config_frozen True
    with patch("app.core.freeze_guard.get_config_freeze_state", return_value=None):
        result = check_freeze(RunMode.LIVE)
    assert result.allowed is True
    assert result.config_frozen is True


def test_record_run_persists_state():
    """record_run does not raise and persists so next check_freeze can compare."""
    snapshot = build_critical_config_snapshot()
    try:
        record_run(snapshot, RunMode.DRY_RUN)
    except Exception as e:
        pytest.fail(f"record_run should not raise: {e}")
    # After record_run, get_config_freeze_state should return our hash (if DB available)
    from app.core.persistence import get_config_freeze_state
    state = get_config_freeze_state()
    if state is not None:
        assert state.get("config_hash") == hash_snapshot(snapshot)
        assert state.get("run_mode") == "DRY_RUN"
