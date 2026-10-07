# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R70-ABCD Batch C — recovery flap, ORATS clocks, notify-on-read."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def test_recovery_excludes_self_job(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from app.core.operations.job_run_store import JobRunStore
    from app.core.operations.jobs import recovery_job

    path = tmp_path / "job_runs.jsonl"
    store = JobRunStore(path=path)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(minutes=5)).isoformat()
    store._append_unlocked(
        {
            "run_id": "rec_self",
            "job_id": "recovery_reconciliation",
            "state": "STARTED",
            "started_at": old,
            "trigger": "startup",
        }
    )
    store._append_unlocked(
        {
            "run_id": "other_1",
            "job_id": "backup",
            "state": "STARTED",
            "started_at": old,
            "trigger": "manual",
        }
    )

    class _StoreFactory:
        def __call__(self, *a, **k):
            return store

    monkeypatch.setattr("app.core.operations.job_run_store.JobRunStore", _StoreFactory())
    with patch("app.core.operations.notification_service.notify_job_recovery") as notify:
        out = recovery_job._run()
    assert "other_1" in out["output_refs"]
    assert "rec_self" not in out["output_refs"]
    notify.assert_called_once()


def test_orats_hard_stale_escalates_to_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import data_health as dh

    ancient = (datetime.now(timezone.utc) - timedelta(days=165)).isoformat()
    monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", ancient)
    monkeypatch.setattr(dh, "_LAST_ERROR_AT", None)
    monkeypatch.setattr(dh, "_get_effective_orats_timestamp", lambda: (ancient, "live_probe", "test"))
    monkeypatch.setattr(dh, "_orats_error_minutes", lambda: 1440)
    assert dh._compute_sticky_status(ancient) == "ERROR"
    fresh = dh.get_orats_freshness_state()
    assert fresh["state"] == "ERROR"


def test_get_data_health_does_not_append_orats_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import data_health as dh

    monkeypatch.setattr(dh, "_load_persisted_state", lambda: None)
    monkeypatch.setattr(dh, "_compute_sticky_status", lambda *_a, **_k: "WARN")
    monkeypatch.setattr(
        dh,
        "_data_health_state",
        lambda: {"status": "WARN", "last_success_at": "2026-02-27T15:36:44Z"},
    )
    monkeypatch.setattr(dh, "_LAST_SUCCESS_AT", "2026-02-27T15:36:44Z")
    with patch("app.api.notifications_store.append_orats_warn") as warn:
        out = dh.get_data_health()
    warn.assert_not_called()
    assert out["status"] == "WARN"
    assert "provider_last_success_at" in out
    assert "provider_connectivity_status" in out
