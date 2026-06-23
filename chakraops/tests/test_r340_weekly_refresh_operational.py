# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — operational weekly universe refresh (Phase 1).

Proves the refresh actually applies the deterministic weekly universe to the
canonical overlay store, appends exactly one history record, is idempotent per
ISO week, is atomic (no partial apply on failure), and that history reconciles
with the active universe.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.universe import universe_overrides as ov
from app.core.universe.refresh_history_store import RefreshHistoryStore
from app.core.universe.weekly_refresh import (
    OUTCOME_APPLIED,
    OUTCOME_SKIPPED_IDEMPOTENT,
    WeeklyRefreshError,
    apply_weekly_universe_refresh,
)

AS_OF = date(2026, 6, 22)
BASE = ["SPY", "QQQ"]
MANIFEST = {"tiers": [{"enabled": True, "symbols": ["AAPL", "MSFT", "SPY"]}], "symbol_overrides": {}}
TARGET = ["AAPL", "MSFT", "SPY"]


@pytest.fixture()
def isolated_stores(tmp_path, monkeypatch):
    # Redirect the overlay file into a temp output dir.
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    ov.reset_overlay()
    store = RefreshHistoryStore(path=tmp_path / "universe_refresh_history.jsonl")
    return store


def test_refresh_applies_and_changes_production_universe(isolated_stores) -> None:
    store = isolated_stores
    out = apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )
    assert out["outcome"] == OUTCOME_APPLIED
    assert ov.get_effective_symbols(BASE) == TARGET
    assert out["applied_added"] == ["AAPL", "MSFT"]
    assert out["applied_removed"] == ["QQQ"]


def test_exactly_one_history_record_appended(isolated_stores) -> None:
    store = isolated_stores
    apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )
    records = store.read_recent(limit=50)
    assert len(records) == 1
    assert records[0]["week_id"] == "2026-W26"
    assert records[0]["symbols"] == TARGET


def test_duplicate_execution_is_idempotent(isolated_stores) -> None:
    store = isolated_stores
    apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )
    again = apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )
    assert again["outcome"] == OUTCOME_SKIPPED_IDEMPOTENT
    # No duplicate weekly record, universe unchanged.
    assert len(store.read_recent(limit=50)) == 1
    assert ov.get_effective_symbols(BASE) == TARGET


def test_failure_does_not_leave_partial_apply(isolated_stores, monkeypatch) -> None:
    store = isolated_stores

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store, "append", _boom)

    with pytest.raises(WeeklyRefreshError):
        apply_weekly_universe_refresh(
            as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
        )

    # Overlay rolled back to the pre-apply (empty) state -> universe == base.
    assert ov.get_effective_symbols(BASE) == sorted(BASE)
    assert store.read_recent(limit=50) == []


def test_history_and_active_universe_reconcile(isolated_stores) -> None:
    store = isolated_stores
    apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )
    last = store.last()
    assert last is not None
    assert sorted(last["symbols"]) == ov.get_effective_symbols(BASE)


def test_dry_run_does_not_mutate(isolated_stores) -> None:
    store = isolated_stores
    out = apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store, dry_run=True
    )
    assert out["outcome"] == "DRY_RUN"
    assert ov.get_effective_symbols(BASE) == sorted(BASE)
    assert store.read_recent(limit=50) == []
