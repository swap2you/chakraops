# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R34.0 — OS-native cross-process refresh lock tests (Windows spawn)."""

from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import pytest

from app.core.universe import refresh_lock


def _configure_coord(coord_dir: str) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord_dir  # type: ignore[method-assign]


def _mp_holder(
    coord_dir: str,
    hold_seconds: float,
    ready_q: multiprocessing.Queue,
    go_evt: multiprocessing.synchronize.Event,
    release_evt: multiprocessing.synchronize.Event | None = None,
) -> None:
    _configure_coord(coord_dir)
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=30.0):
        ready_q.put("holding")
        go_evt.set()
        if release_evt is not None:
            release_evt.wait(timeout=hold_seconds)
        else:
            time.sleep(hold_seconds)


def _mp_try_acquire(
    coord_dir: str,
    timeout: float,
    out_q: multiprocessing.Queue,
    go_evt: multiprocessing.synchronize.Event,
    release_evt: multiprocessing.synchronize.Event | None = None,
) -> None:
    _configure_coord(coord_dir)
    if not go_evt.wait(timeout=30.0):
        out_q.put("timeout")
        return
    try:
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=timeout):
            out_q.put("acquired")
    except refresh_lock.RefreshLockTimeout:
        out_q.put("timeout")
    finally:
        if release_evt is not None:
            release_evt.set()


def _mp_exclusion_worker(
    coord_dir: str,
    active_path: str,
    max_path: str,
    worker_id: int,
    out_q: multiprocessing.Queue,
) -> None:
    _configure_coord(coord_dir)
    active = Path(active_path)
    max_seen = Path(max_path)
    try:
        with refresh_lock.cross_process_lock("weekly_refresh", timeout=30.0):
            current = int(active.read_text(encoding="utf-8") or "0") + 1
            active.write_text(str(current), encoding="utf-8")
            prior_max = int(max_seen.read_text(encoding="utf-8") or "0")
            if current > prior_max:
                max_seen.write_text(str(current), encoding="utf-8")
            time.sleep(0.15)
            active.write_text(str(current - 1), encoding="utf-8")
        out_q.put(f"done-{worker_id}")
    except refresh_lock.RefreshLockTimeout:
        out_q.put(f"timeout-{worker_id}")


def _mp_hold_until_killed(coord_dir: str, ready_q: multiprocessing.Queue) -> None:
    _configure_coord(coord_dir)
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=60.0):
        ready_q.put("holding")
        while True:
            time.sleep(3600)


@pytest.fixture()
def coord(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    return tmp_path


def _spawn_context() -> multiprocessing.context.BaseContext:
    return multiprocessing.get_context("spawn")


def test_mp_mutual_exclusion_at_most_one_holder(coord) -> None:
    ctx = _spawn_context()
    active = coord / "active.count"
    max_seen = coord / "max.count"
    active.write_text("0", encoding="utf-8")
    max_seen.write_text("0", encoding="utf-8")
    out_q: multiprocessing.Queue = ctx.Queue()
    workers = [
        ctx.Process(
            target=_mp_exclusion_worker,
            args=(str(coord), str(active), str(max_seen), i, out_q),
        )
        for i in range(4)
    ]
    for proc in workers:
        proc.start()
    for proc in workers:
        proc.join(timeout=20)
        assert proc.exitcode == 0
    results = [out_q.get(timeout=1) for _ in workers]
    assert all(r.startswith("done-") for r in results)
    assert int(max_seen.read_text(encoding="utf-8")) == 1


def test_mp_long_holder_not_displaced_by_age(coord) -> None:
    ctx = _spawn_context()
    ready_q: multiprocessing.Queue = ctx.Queue()
    out_q: multiprocessing.Queue = ctx.Queue()
    go_evt = ctx.Event()
    holder = ctx.Process(target=_mp_holder, args=(str(coord), 2.0, ready_q, go_evt))
    holder.start()
    assert ready_q.get(timeout=30) == "holding"
    lock_path = refresh_lock._lock_path("weekly_refresh")
    old = time.time() - 9999
    os.utime(lock_path, (old, old))
    waiter = ctx.Process(target=_mp_try_acquire, args=(str(coord), 0.5, out_q, go_evt))
    waiter.start()
    assert out_q.get(timeout=10) == "timeout"
    holder.join(timeout=15)
    assert holder.exitcode == 0
    waiter.join(timeout=10)


def test_mp_lock_timeout_produces_controlled_error(coord) -> None:
    ctx = _spawn_context()
    ready_q: multiprocessing.Queue = ctx.Queue()
    out_q: multiprocessing.Queue = ctx.Queue()
    go_evt = ctx.Event()
    release_evt = ctx.Event()
    holder = ctx.Process(
        target=_mp_holder,
        args=(str(coord), 30.0, ready_q, go_evt, release_evt),
    )
    holder.start()
    assert ready_q.get(timeout=30) == "holding"
    waiter = ctx.Process(
        target=_mp_try_acquire,
        args=(str(coord), 0.25, out_q, go_evt, release_evt),
    )
    waiter.start()
    assert out_q.get(timeout=15) == "timeout"
    holder.join(timeout=15)
    waiter.join(timeout=10)


def test_mp_process_termination_releases_os_lock(coord) -> None:
    ctx = _spawn_context()
    ready_q: multiprocessing.Queue = ctx.Queue()
    out_q: multiprocessing.Queue = ctx.Queue()
    holder = ctx.Process(target=_mp_hold_until_killed, args=(str(coord), ready_q))
    holder.start()
    assert ready_q.get(timeout=5) == "holding"
    holder.terminate()
    holder.join(timeout=10)
    go_evt = ctx.Event()
    go_evt.set()
    acquirer = ctx.Process(target=_mp_try_acquire, args=(str(coord), 5.0, out_q, go_evt))
    acquirer.start()
    assert out_q.get(timeout=10) == "acquired"
    acquirer.join(timeout=10)
    assert acquirer.exitcode == 0


def test_mp_subsequent_acquire_after_release(coord) -> None:
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=2.0):
        pass
    with refresh_lock.cross_process_lock("weekly_refresh", timeout=2.0):
        assert refresh_lock._lock_path("weekly_refresh").exists()


def test_mp_unknown_metadata_does_not_cause_lock_theft(coord) -> None:
    lock_path = refresh_lock._lock_path("weekly_refresh")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text('{"pid":999999999,"lock_id":"dead"}', encoding="utf-8")
    ctx = _spawn_context()
    ready_q: multiprocessing.Queue = ctx.Queue()
    out_q: multiprocessing.Queue = ctx.Queue()
    go_evt = ctx.Event()
    release_evt = ctx.Event()
    holder = ctx.Process(
        target=_mp_holder,
        args=(str(coord), 30.0, ready_q, go_evt, release_evt),
    )
    holder.start()
    assert ready_q.get(timeout=30) == "holding"
    waiter = ctx.Process(
        target=_mp_try_acquire,
        args=(str(coord), 0.5, out_q, go_evt, release_evt),
    )
    waiter.start()
    assert out_q.get(timeout=15) == "timeout"
    holder.join(timeout=15)
    waiter.join(timeout=10)
