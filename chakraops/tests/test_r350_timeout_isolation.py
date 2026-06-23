# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 subprocess timeout isolation tests."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest


def _job_def():
    from app.core.operations.job_registry import JobDefinition

    return JobDefinition(
        job_id="backup",
        purpose="test",
        owner="test",
        schedule_cron="manual",
        timezone="America/New_York",
        lock_name="job_test_timeout",
        timeout_seconds=1.0,
        max_retries=0,
        retry_base_seconds=0.01,
        retry_max_seconds=0.02,
        notification_policy="INFO",
        failure_classification="test",
        manual_command="test",
        recovery_procedure="test",
    )


def test_hanging_job_times_out_and_releases_lock(tmp_path, monkeypatch):
    from app.core.operations.job_executor import JobExecutionError, execute_job
    from app.core.operations.job_run_store import JobRunStore
    from app.core.operations.job_registry import JobRegistry
    from dataclasses import replace

    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    monkeypatch.setenv("CHAKRAOPS_TEST_JOB_BEHAVIOR", "hang")
    store = JobRunStore(path=tmp_path / "runs.jsonl")
    reg = JobRegistry()

    def noop():
        return {"output_refs": []}

    d = replace(_job_def(), job_id="hang_test", lock_name="job_hang_test", timeout_seconds=2.0)
    reg.register(d, noop)
    t0 = time.monotonic()
    with pytest.raises(JobExecutionError):
        execute_job(d, noop, store=store, use_subprocess_timeout=True)
    assert time.monotonic() - t0 < 10.0
    assert store.read_all()[-1]["state"] == "TIMED_OUT"
    monkeypatch.delenv("CHAKRAOPS_TEST_JOB_BEHAVIOR", raising=False)

    d2 = replace(_job_def(), job_id="hang_test2", lock_name="job_hang_test2", timeout_seconds=2.0)
    reg.register(d2, lambda: {"output_refs": ["ok"]})
    result = execute_job(d2, reg.handler("hang_test2"), store=store, use_subprocess_timeout=False)
    assert result["state"] == "SUCCEEDED"
