# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — transaction-safe weekly universe refresh (Phase 1).

Extends the operational tests with concurrency, crash-interruption, failed
rollback, deterministic recovery, and admin-route status mapping. Proves the
refresh is atomic and idempotent under a single cross-process lock, and that an
interrupted transaction is reconciled deterministically.
"""

from __future__ import annotations

import threading
from datetime import date

import pytest

from app.core.universe import refresh_lock
from app.core.universe import universe_overrides as ov
from app.core.universe.refresh_history_store import RefreshHistoryStore
from app.core.universe.weekly_refresh import (
    OUTCOME_APPLIED,
    OUTCOME_SKIPPED_IDEMPOTENT,
    WeeklyRefreshCriticalError,
    WeeklyRefreshError,
    apply_weekly_universe_refresh,
    recover_pending_transaction,
)

AS_OF = date(2026, 6, 22)
WEEK = "2026-W26"
BASE = ["SPY", "QQQ"]
MANIFEST = {"tiers": [{"enabled": True, "symbols": ["AAPL", "MSFT", "SPY"]}], "symbol_overrides": {}}
TARGET = ["AAPL", "MSFT", "SPY"]


@pytest.fixture()
def stores(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    ov.reset_overlay()
    refresh_lock.clear_journal("weekly_refresh")
    return RefreshHistoryStore(path=tmp_path / "universe_refresh_history.jsonl")


def _run(store):
    return apply_weekly_universe_refresh(
        as_of=AS_OF, manifest=MANIFEST, base_symbols=BASE, history_store=store
    )


# --- Concurrency / atomicity ------------------------------------------------

def test_concurrent_same_week_calls_apply_exactly_once(stores) -> None:
    store = stores
    results: list = []
    errors: list = []

    def worker():
        try:
            results.append(_run(store))
        except Exception as e:  # pragma: no cover - defensive
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    applied = [r for r in results if r["outcome"] == OUTCOME_APPLIED]
    skipped = [r for r in results if r["outcome"] == OUTCOME_SKIPPED_IDEMPOTENT]
    assert len(applied) == 1
    assert len(skipped) == 5
    # Exactly one history record and a consistent active universe.
    assert len(store.read_recent(limit=50)) == 1
    assert ov.get_effective_symbols(BASE) == TARGET


def test_same_week_duplicate_is_idempotent_skip(stores) -> None:
    store = stores
    assert _run(store)["outcome"] == OUTCOME_APPLIED
    again = _run(store)
    assert again["outcome"] == OUTCOME_SKIPPED_IDEMPOTENT
    assert len(store.read_recent(limit=50)) == 1


def test_atomic_overlay_write_leaves_no_temp_files(stores, tmp_path) -> None:
    _run(stores)
    leftover = list((tmp_path).glob("**/*.tmp*"))
    assert leftover == []


# --- Crash interruption -----------------------------------------------------

def test_interruption_during_overlay_replacement_rolls_back(stores, monkeypatch) -> None:
    store = stores

    def _boom(*a, **k):
        raise OSError("overlay replace interrupted")

    monkeypatch.setattr(
        "app.core.universe.universe_overrides.apply_effective_universe", _boom
    )
    with pytest.raises(WeeklyRefreshError):
        _run(store)

    # Universe unchanged (== base), nothing recorded, journal cleared.
    assert ov.get_effective_symbols(BASE) == sorted(BASE)
    assert store.read_recent(limit=50) == []
    assert refresh_lock.read_journal("weekly_refresh") is None


def test_interruption_during_history_replacement_rolls_back(stores, monkeypatch) -> None:
    store = stores
    monkeypatch.setattr(store, "append", lambda **k: (_ for _ in ()).throw(OSError("history interrupted")))

    with pytest.raises(WeeklyRefreshError):
        _run(store)

    # Overlay rolled back to base; no history; journal cleared.
    assert ov.get_effective_symbols(BASE) == sorted(BASE)
    assert store.read_recent(limit=50) == []
    assert refresh_lock.read_journal("weekly_refresh") is None


# --- Failed rollback (critical) --------------------------------------------

def test_failed_rollback_raises_critical_and_preserves_journal(stores, monkeypatch) -> None:
    store = stores
    monkeypatch.setattr(store, "append", lambda **k: (_ for _ in ()).throw(OSError("history interrupted")))
    monkeypatch.setattr(
        "app.core.universe.universe_overrides.restore_overlay",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("rollback failed")),
    )

    with pytest.raises(WeeklyRefreshCriticalError):
        _run(store)

    # Journal is preserved as evidence for operator-led recovery.
    journal = refresh_lock.read_journal("weekly_refresh")
    assert journal is not None
    assert journal["week_id"] == WEEK


# --- Deterministic recovery / reconciliation -------------------------------

def test_recovery_rolls_back_uncommitted_transaction(stores) -> None:
    store = stores
    # Simulate a crash: overlay applied to TARGET, journal present, but the
    # history commit never happened.
    ov.apply_effective_universe(TARGET, BASE)
    refresh_lock.write_journal(
        "weekly_refresh",
        {"week_id": WEEK, "phase": "history", "prev_overlay": {"added": [], "removed": []}},
    )

    out = recover_pending_transaction(history_store=store)
    assert out == {"recovered": "ROLLED_BACK", "week_id": WEEK}
    assert ov.get_effective_symbols(BASE) == sorted(BASE)
    assert refresh_lock.read_journal("weekly_refresh") is None


def test_recovery_keeps_committed_transaction(stores) -> None:
    store = stores
    # Simulate a crash AFTER the commit: history has the record and overlay is
    # already at TARGET; journal still present.
    ov.apply_effective_universe(TARGET, BASE)
    store.append(week_id=WEEK, symbols=TARGET, reason_codes=["ADDED"])
    refresh_lock.write_journal(
        "weekly_refresh",
        {"week_id": WEEK, "phase": "history", "prev_overlay": {"added": [], "removed": []}},
    )

    out = recover_pending_transaction(history_store=store)
    assert out == {"recovered": "COMMITTED", "week_id": WEEK}
    # Committed state preserved.
    assert ov.get_effective_symbols(BASE) == TARGET
    assert refresh_lock.read_journal("weekly_refresh") is None


def test_refresh_recovers_pending_then_applies(stores) -> None:
    store = stores
    # Leftover uncommitted transaction from a crash.
    ov.apply_effective_universe(["TSLA"], BASE)
    refresh_lock.write_journal(
        "weekly_refresh",
        {"week_id": "2026-W25", "phase": "history", "prev_overlay": {"added": [], "removed": []}},
    )

    out = _run(store)
    assert out["outcome"] == OUTCOME_APPLIED
    assert ov.get_effective_symbols(BASE) == TARGET
    assert len(store.read_recent(limit=50)) == 1


# --- Admin route status mapping --------------------------------------------

def test_admin_route_returns_controlled_status(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import app.core.universe.weekly_refresh as wr
    from app.api.server import app

    monkeypatch.setattr(
        wr,
        "apply_weekly_universe_refresh",
        lambda **k: {"outcome": OUTCOME_APPLIED, "week_id": WEEK, "applied_added": [], "applied_removed": []},
    )
    resp = TestClient(app).post("/api/ui/universe/weekly-refresh/apply", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPLIED"


def test_admin_route_maps_critical_failure(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import app.core.universe.weekly_refresh as wr
    from app.api.server import app

    def _critical(**k):
        raise WeeklyRefreshCriticalError("rollback failed; journal preserved")

    monkeypatch.setattr(wr, "apply_weekly_universe_refresh", _critical)
    resp = TestClient(app).post("/api/ui/universe/weekly-refresh/apply", json={})
    assert resp.status_code == 500
    assert resp.json()["detail"]["status"] == "CRITICAL"
    assert resp.json()["detail"]["reason_code"] == "REFRESH_RECOVERY_FAILED"
