# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.2 — Universe V2 store tests (transactional persistence, versioning, fail-closed)."""

from pathlib import Path

import pytest

from app.core.universe_v2 import store
from app.core.universe_v2.model import UniverseV2Record, UniverseV2Snapshot


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    base = tmp_path / "universe_v2"
    base.mkdir(parents=True, exist_ok=True)
    lockdir = tmp_path / "locks"
    lockdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "_base_dir", lambda: base)
    # Isolate the cross-process lock/journal directory too.
    import app.core.universe.refresh_lock as rl
    monkeypatch.setattr(rl, "_coord_dir", lambda: lockdir)
    yield base


def _snap(version, records=None):
    return UniverseV2Snapshot(
        version=version, created_at_utc="2026-07-12T00:00:00+00:00",
        research_pool_count=len(records or []), records=records or [],
        counts={"total_records": len(records or [])},
    )


def test_load_state_missing_is_empty():
    s = store.load_state()
    assert s["version"] == 0
    assert s["symbols"] == {}


def test_save_and_load_state():
    store.save_state({"schema_version": "univ2.v1", "version": 2, "symbols": {"AAPL": {"lifecycle_state": "WATCH"}}})
    s = store.load_state()
    assert s["version"] == 2
    assert s["symbols"]["AAPL"]["lifecycle_state"] == "WATCH"


def test_backup_and_restore_state():
    store.save_state({"schema_version": "univ2.v1", "version": 1, "symbols": {"AAPL": {"lifecycle_state": "ADMITTED"}}})
    assert store.backup_state() is True
    store.save_state({"schema_version": "univ2.v1", "version": 2, "symbols": {"AAPL": {"lifecycle_state": "QUARANTINE"}}})
    assert store.restore_state() is True
    s = store.load_state()
    assert s["version"] == 1
    assert s["symbols"]["AAPL"]["lifecycle_state"] == "ADMITTED"


def test_publish_snapshot_and_get_latest():
    snap = _snap(1, [UniverseV2Record(symbol="AAPL")])
    store.publish_snapshot(snap, {"schema_version": "univ2.v1", "version": 1, "symbols": {}})
    got = store.get_latest_snapshot()
    assert got is not None
    assert got.version == 1
    assert got.records[0].symbol == "AAPL"


def test_versioned_files_written_and_pruned():
    for v in range(1, store.SNAPSHOT_KEEP + 4):
        store.publish_snapshot(_snap(v), {"schema_version": "univ2.v1", "version": v, "symbols": {}})
    versions_dir = store._snapshots_dir()
    files = sorted(p.name for p in versions_dir.iterdir() if p.suffix == ".json")
    assert len(files) == store.SNAPSHOT_KEEP  # oldest pruned
    # latest points at the newest version
    assert store.get_latest_snapshot().version == store.SNAPSHOT_KEEP + 3


def test_get_latest_corrupt_is_fail_closed():
    store.publish_snapshot(_snap(1), {"schema_version": "univ2.v1", "version": 1, "symbols": {}})
    # Corrupt the latest file.
    store._snapshot_latest_path().write_text("{ not json", encoding="utf-8")
    assert store.get_latest_snapshot() is None


def test_load_state_corrupt_is_fail_closed():
    store._state_path().write_text("garbage", encoding="utf-8")
    s = store.load_state()
    assert s["version"] == 0 and s["symbols"] == {}


def _publish_v1():
    store.publish_snapshot(_snap(1, [UniverseV2Record(symbol="AAPL")]),
                           {"schema_version": "univ2.v1", "version": 1, "symbols": {"AAPL": {}}})


def _fail_publish_on(monkeypatch, filename):
    import app.core.universe.refresh_lock as rl
    real_write = rl.atomic_write_json

    def failing_write(path, data):
        if str(path).endswith(filename):
            raise OSError("disk full")
        return real_write(path, data)

    monkeypatch.setattr(rl, "atomic_write_json", failing_write)
    with pytest.raises(OSError):
        store.publish_snapshot(_snap(2, [UniverseV2Record(symbol="AAPL")]),
                               {"schema_version": "univ2.v1", "version": 2, "symbols": {"AAPL": {}}})


def test_publish_failure_on_state_write_keeps_previous_version(monkeypatch):
    _publish_v1()
    assert store.get_latest_snapshot().version == 1
    _fail_publish_on(monkeypatch, "lifecycle_state.json")
    # Both latest and durable state remain at the previous good v1 (no divergence).
    assert store.get_latest_snapshot().version == 1
    assert store.load_state()["version"] == 1


def test_publish_failure_on_latest_swap_rolls_back_state(monkeypatch):
    _publish_v1()
    assert store.get_latest_snapshot().version == 1
    # State is written before the latest swap; if the latest swap fails, durable state must be
    # rolled back so it never advances past the served snapshot.
    _fail_publish_on(monkeypatch, "snapshot_latest.json")
    assert store.get_latest_snapshot().version == 1
    assert store.load_state()["version"] == 1
