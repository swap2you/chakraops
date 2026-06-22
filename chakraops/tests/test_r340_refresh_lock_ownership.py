# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — ownership-safe cross-process refresh lock tests."""

from __future__ import annotations

import json
import multiprocessing
import os
import time

import pytest

from app.core.universe import refresh_lock


def _hold_lock(coord_dir: str, hold_seconds: float) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord_dir  # type: ignore[method-assign]
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=5.0):
        time.sleep(hold_seconds)


def _try_acquire(coord_dir: str, timeout: float, out_q: multiprocessing.Queue) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord_dir  # type: ignore[method-assign]
    try:
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=timeout):
            out_q.put("acquired")
    except refresh_lock.RefreshLockTimeout:
        out_q.put("timeout")


@pytest.fixture()
def coord(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    return tmp_path


def test_live_lock_older_than_stale_threshold_is_not_stolen(coord) -> None:
    lock_path = refresh_lock._lock_path("weekly_refresh")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "lock_id": "live-lock",
        "pid": os.getpid(),
        "hostname": refresh_lock._hostname(),
        "created_at": time.time() - 9999,
        "process_start_epoch": refresh_lock._process_creation_epoch(os.getpid()),
    }
    lock_path.write_text(json.dumps(meta), encoding="utf-8")
    # Backdate mtime so age-only logic would have stolen this lock pre-remediation.
    old = time.time() - 9999
    os.utime(lock_path, (old, old))

    with pytest.raises(refresh_lock.RefreshLockTimeout):
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=0.25):
            pass


def test_dead_owner_lock_is_reclaimed_safely(coord) -> None:
    lock_path = refresh_lock._lock_path("weekly_refresh")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "lock_id": "dead-lock",
        "pid": 999_999_999,
        "hostname": refresh_lock._hostname(),
        "created_at": time.time(),
        "process_start_epoch": 1.0,
    }
    lock_path.write_text(json.dumps(meta), encoding="utf-8")

    with refresh_lock.cross_process_lock("weekly_refresh", timeout=2.0):
        assert lock_path.exists()


def test_pid_reuse_protection_treats_mismatched_start_as_dead(coord, monkeypatch) -> None:
    lock_path = refresh_lock._lock_path("weekly_refresh")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "lock_id": "reuse-lock",
        "pid": os.getpid(),
        "hostname": refresh_lock._hostname(),
        "created_at": time.time(),
        "process_start_epoch": 1.0,
    }
    lock_path.write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(
        refresh_lock,
        "_process_creation_epoch",
        lambda _pid: time.time(),
    )
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=2.0):
        assert lock_path.exists()


def test_ownership_mismatch_on_release_raises(coord) -> None:
    with pytest.raises(refresh_lock.RefreshLockOwnershipError):
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=2.0) as meta:
            lock_path = refresh_lock._lock_path("weekly_refresh")
            tampered = dict(meta)
            tampered["lock_id"] = "other-holder"
            lock_path.write_text(json.dumps(tampered), encoding="utf-8")


def test_concurrent_subprocess_contention_one_holder(coord) -> None:
    if os.name == "nt":
        pytest.skip("subprocess lock timing flaky on some Windows CI hosts")
    out_q: multiprocessing.Queue = multiprocessing.Queue()
    holder = multiprocessing.Process(target=_hold_lock, args=(str(coord), 1.5))
    waiter = multiprocessing.Process(
        target=_try_acquire, args=(str(coord), 0.5, out_q)
    )
    holder.start()
    time.sleep(0.2)
    waiter.start()
    holder.join(timeout=5)
    waiter.join(timeout=5)
    assert out_q.get(timeout=1) == "timeout"


def test_lock_timeout_produces_controlled_error(coord) -> None:
    lock_path = refresh_lock._lock_path("weekly_refresh")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "lock_id": "blocker",
        "pid": os.getpid(),
        "hostname": refresh_lock._hostname(),
        "created_at": time.time(),
        "process_start_epoch": refresh_lock._process_creation_epoch(os.getpid()),
    }
    lock_path.write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(refresh_lock.RefreshLockTimeout, match="within"):
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=0.15):
            pass
