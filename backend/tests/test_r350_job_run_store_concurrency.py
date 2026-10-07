# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 JobRunStore Windows multiprocessing concurrency tests."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest


def _writer(coord: str, job_id: str, n: int, out_q: multiprocessing.Queue) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord  # type: ignore[method-assign]
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore()
    for i in range(n):
        run = store.start_run(job_id=f"{job_id}_{i}", trigger="test")
        store.finish_run(run["run_id"], state="SUCCEEDED", output_refs=[str(i)])
    out_q.put("done")


def test_concurrent_writers_no_lost_records(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    out_q: multiprocessing.Queue = ctx.Queue()
    workers = [
        ctx.Process(target=_writer, args=(str(tmp_path), f"w{w}", 5, out_q))
        for w in range(3)
    ]
    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    for _ in workers:
        assert out_q.get(timeout=5) == "done"

    import app.core.settings as settings

    settings.get_output_dir = lambda: str(tmp_path)  # type: ignore[method-assign]
    from app.core.operations.job_run_store import JobRunStore

    runs = JobRunStore().read_all(limit=1000)
    assert len(runs) == 15
    assert all(r["state"] == "SUCCEEDED" for r in runs)


def test_terminal_state_cannot_regress(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations.job_run_store import JobRunStore, JobRunStoreError

    store = JobRunStore()
    run = store.start_run(job_id="x", trigger="manual")
    store.finish_run(run["run_id"], state="SUCCEEDED")
    with pytest.raises(JobRunStoreError):
        store.finish_run(run["run_id"], state="FAILED")
