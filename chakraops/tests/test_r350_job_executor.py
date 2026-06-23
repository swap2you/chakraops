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

    result = execute_job(_job_def(), ok, store=store, use_subprocess_timeout=False)
    assert result["state"] == "SUCCEEDED"


def test_execute_job_timeout_uses_subprocess_isolation(tmp_path, monkeypatch):
    """Thread timeout is replaced by subprocess isolation — see test_r350_timeout_isolation."""
    monkeypatch.setenv("CHAKRAOPS_TEST_JOB_BEHAVIOR", "hang")
    from dataclasses import replace

    from app.core.operations.job_executor import JobExecutionError, execute_job
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    fast = replace(_job_def(), job_id="timeout_job", lock_name="job_timeout_job", timeout_seconds=2.0, max_retries=0)

    def noop():
        return {"output_refs": []}

    with pytest.raises(JobExecutionError):
        execute_job(fast, noop, store=store, use_subprocess_timeout=True)
    assert store.read_all()[-1]["state"] == "TIMED_OUT"
    monkeypatch.delenv("CHAKRAOPS_TEST_JOB_BEHAVIOR", raising=False)


def test_safe_error_redaction(tmp_path):
    from app.core.operations.job_executor import JobExecutionError, execute_job
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    d = _job_def()

    def boom():
        raise RuntimeError("token=supersecret12345")

    with patch("app.core.operations.notification_service.notify_job_failure"):
        with pytest.raises(JobExecutionError) as exc:
            execute_job(d, boom, store=store, use_subprocess_timeout=False)
    assert "supersecret" not in str(exc.value).lower() or "redact" in str(exc.value).lower()
