# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 recovery interrupted runs."""

from __future__ import annotations

from pathlib import Path


def test_recovery_job_marks_interrupted(tmp_path, monkeypatch):
    from app.core.operations.job_run_store import JobRunStore
    from app.core.operations.jobs.recovery_job import _run

    path = tmp_path / "runs.jsonl"
    JobRunStore(path=path).start_run(job_id="backup", trigger="schedule")
    monkeypatch.setattr("app.core.operations.job_run_store._runs_path", lambda: path)
    result = _run()
    assert result["metadata"]["count"] >= 1
    assert JobRunStore(path=path).interrupted_started_runs() == []
