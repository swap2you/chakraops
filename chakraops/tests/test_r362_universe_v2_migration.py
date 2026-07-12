# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 migration tests (conservative, idempotent, rollback)."""

import pytest

from app.core.universe_v2 import migration, store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    base = tmp_path / "universe_v2"
    base.mkdir(parents=True, exist_ok=True)
    lockdir = tmp_path / "locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "_base_dir", lambda: base)
    import app.core.universe.refresh_lock as rl
    monkeypatch.setattr(rl, "_coord_dir", lambda: lockdir)
    # Deterministic pool + removals.
    monkeypatch.setattr(migration, "_effective_and_removed", lambda: (["AAPL", "MSFT", "NVDA"], ["OLD"]))
    yield base


def test_conservative_init_watch_and_removed():
    state = migration.initialize_universe_v2()
    syms = state["symbols"]
    assert syms["AAPL"]["lifecycle_state"] == "WATCH"
    assert syms["MSFT"]["lifecycle_state"] == "WATCH"
    assert syms["OLD"]["lifecycle_state"] == "REMOVED"
    # No auto-admission.
    assert all(v["lifecycle_state"] != "ADMITTED" for v in syms.values())
    # Streaks start at 0.
    assert syms["AAPL"]["pass_streak"] == 0 and syms["AAPL"]["fail_streak"] == 0


def test_migration_is_idempotent():
    first = migration.initialize_universe_v2()
    second = migration.initialize_universe_v2()
    assert first["symbols"] == second["symbols"]
    # Re-run made no destructive change.
    assert set(second["symbols"].keys()) == {"AAPL", "MSFT", "NVDA", "OLD"}


def test_migration_preserves_existing_state_and_adds_new(monkeypatch):
    migration.initialize_universe_v2()
    # Mutate an existing symbol to a non-default state, then add a new pool symbol.
    st = store.load_state()
    st["symbols"]["AAPL"]["lifecycle_state"] = "ADMITTED"
    st["symbols"]["AAPL"]["pass_streak"] = 5
    store.save_state(st)
    monkeypatch.setattr(migration, "_effective_and_removed", lambda: (["AAPL", "MSFT", "NVDA", "TSLA"], ["OLD"]))
    migration.initialize_universe_v2()
    st2 = store.load_state()
    # Existing state preserved (not reset).
    assert st2["symbols"]["AAPL"]["lifecycle_state"] == "ADMITTED"
    assert st2["symbols"]["AAPL"]["pass_streak"] == 5
    # New symbol added conservatively.
    assert st2["symbols"]["TSLA"]["lifecycle_state"] == "WATCH"


def test_rollback_restores_prior_state():
    migration.initialize_universe_v2()  # backup is empty->none; establish state
    st = store.load_state()
    st["symbols"]["AAPL"]["lifecycle_state"] = "ADMITTED"
    store.save_state(st)
    store.backup_state()  # backup ADMITTED state
    st["symbols"]["AAPL"]["lifecycle_state"] = "QUARANTINE"
    store.save_state(st)
    assert migration.rollback() is True
    assert store.load_state()["symbols"]["AAPL"]["lifecycle_state"] == "ADMITTED"
