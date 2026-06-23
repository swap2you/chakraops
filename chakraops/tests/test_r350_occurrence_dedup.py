# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 occurrence dedup tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def occ_path(tmp_path, monkeypatch):
    path = tmp_path / "occurrences.jsonl"
    monkeypatch.setattr("app.core.operations.occurrence_store._store_path", lambda: path)
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    return path


def test_same_hour_poll_runs_once(occ_path, monkeypatch):
    from app.core.operations.occurrence_store import is_completed, mark_completed, occurrence_key
    from app.core.operations import scheduler_service as svc

    svc.reset_scheduler_state_for_tests()
    monkeypatch.setenv("CHAKRAOPS_JOB_BACKUP_ENABLED", "true")
    now = datetime(2026, 6, 23, 2, 15, tzinfo=ZoneInfo("America/New_York"))
    key = occurrence_key("backup", now)
    calls = {"n": 0}

    def fake_run(job_id, *, trigger="manual"):
        calls["n"] += 1
        return {"run_id": "x", "state": "SUCCEEDED"}

    with patch.object(svc, "run_job_now", side_effect=fake_run):
        r1 = svc.run_due_jobs(now)
        r2 = svc.run_due_jobs(now)
    assert calls["n"] == 1
    assert "backup" in r1["executed"]
    assert r2["executed"] == []
    assert is_completed(key)


def test_restart_does_not_rerun_completed_occurrence(occ_path, monkeypatch):
    from app.core.operations.occurrence_store import mark_completed, occurrence_key
    from app.core.operations import scheduler_service as svc

    now = datetime(2026, 6, 23, 2, 5, tzinfo=ZoneInfo("America/New_York"))
    key = occurrence_key("backup", now)
    mark_completed(key)
    monkeypatch.setenv("CHAKRAOPS_JOB_BACKUP_ENABLED", "true")
    with patch.object(svc, "run_job_now") as mock_run:
        result = svc.run_due_jobs(now)
    mock_run.assert_not_called()
    assert key in result["skipped_occurrences"]
