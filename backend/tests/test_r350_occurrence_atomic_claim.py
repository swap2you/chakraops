# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 atomic occurrence claim — Windows spawn multiprocessing tests."""

from __future__ import annotations

import multiprocessing
import time
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest


def _configure_store(coord: str) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord  # type: ignore[method-assign]


def _claim_worker(coord: str, key: str, job_id: str, slot: str, out_q: multiprocessing.Queue) -> None:
    _configure_store(coord)
    from app.core.operations.occurrence_store import claim_occurrence

    run_id = str(uuid.uuid4())
    result = claim_occurrence(key, job_id=job_id, run_id=run_id, scheduled_at=slot)
    out_q.put(result["status"])


def test_simultaneous_claim_exactly_one_winner(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    out_q: multiprocessing.Queue = ctx.Queue()
    key = "backup|2026-06-23T02:00"
    workers = [
        ctx.Process(target=_claim_worker, args=(str(tmp_path), key, "backup", "2026-06-23T02:00", out_q))
        for _ in range(4)
    ]
    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    statuses = [out_q.get(timeout=5) for _ in workers]
    assert statuses.count("CLAIMED") == 1
    assert statuses.count("ALREADY_CLAIMED") == 3


def test_completed_occurrence_cannot_be_reclaimed(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations.occurrence_store import (
        claim_occurrence,
        complete_occurrence,
        is_completed,
    )

    key = "backup|2026-06-23T02:00"
    first = claim_occurrence(key, job_id="backup", run_id="r1", scheduled_at="2026-06-23T02:00")
    complete_occurrence(key, first["claim_id"])
    second = claim_occurrence(key, job_id="backup", run_id="r2", scheduled_at="2026-06-23T02:00")
    assert second["status"] == "ALREADY_COMPLETED"
    assert is_completed(key)


def test_interrupted_claim_recovery_after_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    import app.core.operations.occurrence_store as occ

    monkeypatch.setattr(occ, "CLAIM_TTL_SECONDS", 1)
    from app.core.operations.occurrence_store import claim_occurrence, complete_occurrence

    key = "backup|2026-06-23T02:00"
    first = claim_occurrence(key, job_id="backup", run_id="r1", scheduled_at="2026-06-23T02:00")
    assert first["status"] == "CLAIMED"
    time.sleep(1.2)
    second = claim_occurrence(key, job_id="backup", run_id="r2", scheduled_at="2026-06-23T02:00")
    assert second["status"] == "CLAIMED"
    complete_occurrence(key, second["claim_id"])


def test_ownership_mismatch_on_completion(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations.occurrence_store import (
        OccurrenceOwnershipError,
        claim_occurrence,
        complete_occurrence,
    )

    key = "backup|2026-06-23T02:00"
    claim = claim_occurrence(key, job_id="backup", run_id="r1", scheduled_at="2026-06-23T02:00")
    with pytest.raises(OccurrenceOwnershipError):
        complete_occurrence(key, "wrong-claim-id")


def test_scheduler_restart_skips_completed_window(tmp_path, monkeypatch):
    from unittest.mock import patch

    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations import scheduler_service as svc
    from app.core.operations.occurrence_store import (
        claim_occurrence,
        complete_occurrence,
        occurrence_key,
    )

    now = datetime(2026, 6, 23, 2, 15, tzinfo=ZoneInfo("America/New_York"))
    key = occurrence_key("backup", now)
    claim = claim_occurrence(
        key,
        job_id="backup",
        run_id="prior",
        scheduled_at="2026-06-23T02:00",
    )
    complete_occurrence(key, claim["claim_id"])
    monkeypatch.setenv("CHAKRAOPS_JOB_BACKUP_ENABLED", "true")
    calls = {"n": 0}

    def fake_run(job_id, *, trigger="manual", run_id=None):
        calls["n"] += 1
        return {"run_id": run_id, "state": "SUCCEEDED"}

    with patch.object(svc, "run_job_now", side_effect=fake_run):
        result = svc.run_due_jobs(now)
    assert calls["n"] == 0
    assert key in result["skipped_occurrences"]


def _claim_and_execute(coord: str, key: str, exec_q: multiprocessing.Queue, out_q: multiprocessing.Queue) -> None:
    _configure_store(coord)
    from app.core.operations.occurrence_store import claim_occurrence, complete_occurrence

    claim = claim_occurrence(key, job_id="backup", run_id=str(uuid.uuid4()), scheduled_at="2026-06-23T02:00")
    if claim["status"] == "CLAIMED":
        exec_q.put(1)
        complete_occurrence(key, claim["claim_id"])
    out_q.put(claim["status"])


def test_exactly_one_job_execution_under_contention(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    exec_q: multiprocessing.Queue = ctx.Queue()
    out_q: multiprocessing.Queue = ctx.Queue()
    key = "backup|2026-06-23T02:00"
    workers = [
        ctx.Process(target=_claim_and_execute, args=(str(tmp_path), key, exec_q, out_q))
        for _ in range(3)
    ]
    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    executions = 0
    while not exec_q.empty():
        executions += exec_q.get()
    assert executions == 1
