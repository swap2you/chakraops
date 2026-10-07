# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 EOD skipped semantics tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest


def test_non_trading_day_fields():
    from app.core.eval.eod_chain_snapshot import run_eod_chain_snapshot_job

    with patch("app.core.eval.eod_chain_snapshot.should_run_eod_chain_today", return_value=False):
        result = run_eod_chain_snapshot_job()
    assert result["skipped"] is True
    assert result["skipped_reason"] == "NON_TRADING_DAY"
    assert result["written_count"] == 0
    assert "skipped" not in result or isinstance(result["skipped"], bool)


def test_empty_universe_fields():
    from app.core.eval.eod_chain_snapshot import run_eod_chain_snapshot_job

    with patch("app.core.eval.eod_chain_snapshot.should_run_eod_chain_today", return_value=True):
        with patch("app.api.data_health.UNIVERSE_SYMBOLS", []):
            result = run_eod_chain_snapshot_job()
    assert result["skipped_reason"] == "EMPTY_UNIVERSE"


def test_executor_records_skipped(tmp_path, monkeypatch):
    from app.core.operations.job_executor import execute_job
    from app.core.operations.job_registry import JobDefinition, JobRegistry

    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore(path=tmp_path / "runs.jsonl")
    reg = JobRegistry()

    def skip_handler():
        return {"skipped": True, "metadata": {"skipped": True, "skipped_reason": "NON_TRADING_DAY"}}

    reg.register(
        JobDefinition(
            job_id="eod_skip_test",
            purpose="t",
            owner="t",
            schedule_cron="m",
            timezone="America/New_York",
            lock_name="job_eod_skip_test",
            timeout_seconds=0,
            max_retries=0,
            retry_base_seconds=1,
            retry_max_seconds=1,
            notification_policy="INFO",
            failure_classification="t",
            manual_command="t",
            recovery_procedure="t",
        ),
        skip_handler,
    )
    result = execute_job(
        reg.get("eod_skip_test"),
        skip_handler,
        store=store,
        use_subprocess_timeout=False,
    )
    assert result["state"] == "SKIPPED"
    assert store.read_all()[-1]["state"] == "SKIPPED"
