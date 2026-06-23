# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 job run store tests."""

from __future__ import annotations

from pathlib import Path


def test_job_run_lifecycle(tmp_path):
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    run = store.start_run(job_id="backup", trigger="manual")
    run_id = run["run_id"]
    store.finish_run(run_id, state="SUCCEEDED", output_refs=["b1"])
    all_runs = store.read_all()
    assert len(all_runs) == 1
    assert all_runs[0]["state"] == "SUCCEEDED"
    assert all_runs[0]["output_refs"] == ["b1"]


def test_interrupted_started_runs(tmp_path):
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    store.start_run(job_id="eod_data_refresh", trigger="schedule")
    interrupted = store.interrupted_started_runs()
    assert len(interrupted) == 1
    store.mark_recovered(interrupted[0]["run_id"], "startup recovery")
    assert store.interrupted_started_runs() == []
