# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 scheduler safety tests."""

from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest


def test_master_scheduler_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_SCHEDULER_ENABLED", raising=False)
    from app.core.operations.scheduler_service import is_master_enabled

    assert is_master_enabled() is False


def test_legacy_schedulers_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CHAKRAOPS_LEGACY_SCHEDULERS_ENABLED", raising=False)
    from app.core.operations.scheduler_service import legacy_schedulers_enabled

    assert legacy_schedulers_enabled() is False


def test_schedule_due_weekly_sunday(monkeypatch):
    monkeypatch.setenv("CHAKRAOPS_JOB_WEEKLY_UNIVERSE_REFRESH_ENABLED", "true")
    from app.core.operations.scheduler_service import run_due_jobs

    sunday = datetime(2026, 6, 28, 6, 0, tzinfo=ZoneInfo("America/New_York"))
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.core.operations.scheduler_service.execute_job",
            lambda *a, **k: {"run_id": "x", "state": "SUCCEEDED"},
        )
        result = run_due_jobs(sunday)
    assert "weekly_universe_refresh" in result["executed"]


def test_no_duplicate_registry_on_scheduler_start(monkeypatch):
    from app.core.operations.job_registry import get_job_registry
    from app.core.operations import scheduler_service as svc

    svc.reset_scheduler_state_for_tests()
    before = len(get_job_registry().list_jobs())
    monkeypatch.setenv("CHAKRAOPS_SCHEDULER_ENABLED", "false")
    svc.start_scheduler_service()
    svc.start_scheduler_service()
    after = len(get_job_registry().list_jobs())
    svc.stop_scheduler_service()
    assert before == after
