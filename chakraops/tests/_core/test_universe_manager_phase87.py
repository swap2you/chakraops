# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.7: Universe Manifest + Tiered Scheduler."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.core.universe.universe_manager import get_symbols_for_cycle, load_universe_manifest
from app.core.universe.universe_state_store import UniverseStateStore


def test_load_manifest_missing_returns_default(tmp_path: Path):
    """load_universe_manifest returns safe default when file missing."""
    path = tmp_path / "nonexistent" / "universe.json"
    manifest = load_universe_manifest(path)
    assert isinstance(manifest, dict)
    assert "tiers" in manifest
    assert len(manifest["tiers"]) >= 1
    assert manifest["tiers"][0]["name"] == "CORE"
    assert "symbols" in manifest["tiers"][0]
    assert manifest.get("max_symbols_per_cycle", 25) >= 1


def test_tier_due_logic_respects_cadence(tmp_path: Path):
    """Tier is due only when (now - last_run) >= cadence_minutes."""
    state_path = tmp_path / "universe_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = UniverseStateStore(state_path)

    manifest = {
        "version": 1,
        "max_symbols_per_cycle": 25,
        "tiers": [
            {"name": "CORE", "enabled": True, "cadence_minutes": 30, "symbols": ["SPY", "QQQ"]},
        ],
        "symbol_overrides": {},
    }

    now = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
    symbols = get_symbols_for_cycle(manifest, now, store)
    assert len(symbols) >= 1
    assert "SPY" in symbols or "QQQ" in symbols

    # Immediate next call: last_run was just now, cadence 30 min -> tier not due
    now_plus_1min = datetime(2026, 2, 13, 12, 1, 0, tzinfo=timezone.utc)
    symbols2 = get_symbols_for_cycle(manifest, now_plus_1min, store)
    assert symbols2 == []

    # After 31 min: tier due again
    now_plus_31 = datetime(2026, 2, 13, 12, 31, 0, tzinfo=timezone.utc)
    symbols3 = get_symbols_for_cycle(manifest, now_plus_31, store)
    assert len(symbols3) >= 1


def test_symbol_override_disabled_skips(tmp_path: Path):
    """symbol_overrides[symbol].enabled=false skips that symbol."""
    state_path = tmp_path / "universe_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = UniverseStateStore(state_path)

    manifest = {
        "version": 1,
        "max_symbols_per_cycle": 25,
        "tiers": [
            {"name": "A", "enabled": True, "cadence_minutes": 30, "symbols": ["SPY", "QQQ", "NVDA"]},
        ],
        "symbol_overrides": {"NVDA": {"enabled": False}},
    }

    now = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
    symbols = get_symbols_for_cycle(manifest, now, store)
    assert "NVDA" not in symbols
    assert "SPY" in symbols or "QQQ" in symbols


def test_max_symbols_per_cycle_enforced(tmp_path: Path):
    """max_symbols_per_cycle caps the returned list."""
    state_path = tmp_path / "universe_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = UniverseStateStore(state_path)

    manifest = {
        "version": 1,
        "max_symbols_per_cycle": 3,
        "tiers": [
            {"name": "A", "enabled": True, "cadence_minutes": 30, "symbols": ["A1", "A2", "A3", "A4", "A5"]},
        ],
        "symbol_overrides": {},
    }

    now = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
    symbols = get_symbols_for_cycle(manifest, now, store)
    assert len(symbols) <= 3
    assert len(symbols) >= 1


def test_round_robin_is_stable_and_advances_cursor(tmp_path: Path):
    """Round-robin is stable; cursor advances across runs."""
    state_path = tmp_path / "universe_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = UniverseStateStore(state_path)

    manifest = {
        "version": 1,
        "max_symbols_per_cycle": 2,
        "tiers": [
            {"name": "A", "enabled": True, "cadence_minutes": 1, "symbols": ["A1", "A2", "A3"]},
        ],
        "symbol_overrides": {},
    }

    base = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
    run1 = get_symbols_for_cycle(manifest, base, store)
    # 2 minutes later so tier is due again
    later = datetime(2026, 2, 13, 12, 2, 0, tzinfo=timezone.utc)
    run2 = get_symbols_for_cycle(manifest, later, store)
    # Run1 takes A1, A2. Run2 takes A3, A1 (cursor advanced)
    assert len(run1) == 2
    assert len(run2) == 2
    # Cursor should have advanced - we should see all three across runs
    assert set(run1) | set(run2) == {"A1", "A2", "A3"}


def test_state_store_creates_and_persists(tmp_path: Path):
    """State store creates file if missing and persists updates."""
    state_path = tmp_path / "state" / "universe_state.json"
    assert not state_path.exists()
    store = UniverseStateStore(state_path)

    loaded = store.load()
    assert loaded["tier_last_run_utc"] == {}
    assert loaded["tier_cursor"] == {}

    loaded["tier_last_run_utc"]["CORE"] = "2026-02-13T12:00:00+00:00"
    loaded["tier_cursor"]["CORE"] = 2
    store.save(loaded)

    assert state_path.exists()
    loaded2 = store.load()
    assert loaded2["tier_last_run_utc"]["CORE"] == "2026-02-13T12:00:00+00:00"
    assert loaded2["tier_cursor"]["CORE"] == 2


def test_no_due_tiers_returns_empty_list(tmp_path: Path):
    """When no tiers are due, returns empty list."""
    state_path = tmp_path / "universe_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = UniverseStateStore(state_path)

    manifest = {
        "version": 1,
        "max_symbols_per_cycle": 25,
        "tiers": [
            {"name": "A", "enabled": True, "cadence_minutes": 60, "symbols": ["SPY"]},
        ],
        "symbol_overrides": {},
    }

    now = datetime(2026, 2, 13, 12, 0, 0, tzinfo=timezone.utc)
    run1 = get_symbols_for_cycle(manifest, now, store)
    assert len(run1) >= 1

    # 1 minute later: tier not due (cadence 60)
    now_plus_1 = datetime(2026, 2, 13, 12, 1, 0, tzinfo=timezone.utc)
    run2 = get_symbols_for_cycle(manifest, now_plus_1, store)
    assert run2 == []
