# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 job registry tests."""

from __future__ import annotations

import pytest


def test_job_registry_single_registration():
    from app.core.operations.job_registry import JobDefinition, JobRegistry

    reg = JobRegistry()

    def handler():
        return {"output_refs": []}

    reg.register(
        JobDefinition(
            job_id="test_job",
            purpose="test",
            owner="test",
            schedule_cron="manual",
            timezone="America/New_York",
            lock_name="test_lock",
            timeout_seconds=1.0,
            max_retries=0,
            retry_base_seconds=1.0,
            retry_max_seconds=1.0,
            notification_policy="INFO",
            failure_classification="test",
            manual_command="test",
            recovery_procedure="test",
        ),
        handler,
    )
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(
            JobDefinition(
                job_id="test_job",
                purpose="dup",
                owner="test",
                schedule_cron="manual",
                timezone="America/New_York",
                lock_name="test_lock",
                timeout_seconds=1.0,
                max_retries=0,
                retry_base_seconds=1.0,
                retry_max_seconds=1.0,
                notification_policy="INFO",
                failure_classification="test",
                manual_command="test",
                recovery_procedure="test",
            ),
            handler,
        )


def test_builtin_jobs_registered():
    from app.core.operations.job_registry import get_job_registry

    reg = get_job_registry()
    ids = {j.job_id for j in reg.list_jobs()}
    expected = {
        "weekly_universe_refresh",
        "eod_data_refresh",
        "decision_generation",
        "nightly_reports",
        "backup",
        "provider_health",
        "retention_cleanup",
        "recovery_reconciliation",
    }
    assert expected.issubset(ids)


def test_jobs_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_JOB_WEEKLY_UNIVERSE_REFRESH_ENABLED", raising=False)
    from app.core.operations.job_registry import get_job_registry

    job = get_job_registry().get("weekly_universe_refresh")
    assert job is not None
    assert job.is_enabled() is False
