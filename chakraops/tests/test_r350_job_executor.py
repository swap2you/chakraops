# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 job executor tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _job_def():
    from app.core.operations.job_registry import JobDefinition

    return JobDefinition(
        job_id="test_exec",
        purpose="test",
        owner="test",
        schedule_cron="manual",
        timezone="America/New_York",
        lock_name="job_test_exec",
        timeout_seconds=2.0,
        max_retries=1,
        retry_base_seconds=0.01,
        retry_max_seconds=0.02,
        notification_policy="INFO",
        failure_classification="test",
        manual_command="test",
        recovery_procedure="test",
    )


def test_execute_job_success(tmp_path):
    from app.core.operations.job_executor import execute_job
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")

    def ok():
        return {"output_refs": ["done"]}

    result = execute_job(_job_def(), ok, store=store)
    assert result["state"] == "SUCCEEDED"


def test_execute_job_timeout(tmp_path):
    import time
    from dataclasses import replace

    from app.core.operations.job_executor import JobExecutionError, execute_job
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    fast = replace(_job_def(), timeout_seconds=0.1, max_retries=0)

    def slow():
        time.sleep(1.0)
        return {"output_refs": []}

    with pytest.raises(JobExecutionError):
        execute_job(fast, slow, store=store)
    runs = store.read_all()
    assert runs[-1]["state"] == "TIMED_OUT"


def test_safe_error_redaction(tmp_path):
    from app.core.operations.job_executor import JobExecutionError, execute_job
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    d = _job_def()

    def boom():
        raise RuntimeError("token=supersecret12345")

    with patch("app.core.operations.notification_service.notify_job_failure"):
        with pytest.raises(JobExecutionError) as exc:
            execute_job(d, boom, store=store)
    assert "supersecret" not in str(exc.value).lower() or "redact" in str(exc.value).lower()
