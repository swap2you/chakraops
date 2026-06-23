# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 atomic notification incidents — Windows spawn multiprocessing tests."""

from __future__ import annotations

import multiprocessing
from pathlib import Path

import pytest


def _configure(coord: str, inc_path: Path, notif_path: Path) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord  # type: ignore[method-assign]
    import app.core.operations.incident_store as inc_mod

    inc_mod._path = lambda: inc_path  # type: ignore[method-assign]
    import app.api.notifications_store as ns

    ns._notifications_path = lambda: notif_path  # type: ignore[method-assign]


def _open_incident_worker(coord: str, inc_path: str, notif_path: str, out_q: multiprocessing.Queue) -> None:
    _configure(coord, Path(inc_path), Path(notif_path))
    from app.core.operations.incident_store import open_incident_if_absent

    result = open_incident_if_absent("backup", "CRITICAL")
    out_q.put((result["incident_id"], result["created"]))


def test_concurrent_incident_creation_exactly_one_open(tmp_path):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    ctx = multiprocessing.get_context("spawn")
    out_q: multiprocessing.Queue = ctx.Queue()
    workers = [
        ctx.Process(
            target=_open_incident_worker,
            args=(str(tmp_path), str(inc_path), str(notif_path), out_q),
        )
        for _ in range(4)
    ]
    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    results = [out_q.get(timeout=5) for _ in workers]
    ids = {r[0] for r in results}
    assert len(ids) == 1
    assert sum(1 for r in results if r[1]) == 1


def _notify_failure_worker(coord: str, inc_path: str, notif_path: str, out_q: multiprocessing.Queue) -> None:
    _configure(coord, Path(inc_path), Path(notif_path))
    from app.core.operations.notification_service import notify_job_failure

    notify_job_failure("backup", "disk full", "CRITICAL")
    out_q.put("done")


def test_concurrent_duplicate_notifications_deduped(tmp_path):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    ctx = multiprocessing.get_context("spawn")
    out_q: multiprocessing.Queue = ctx.Queue()
    workers = [
        ctx.Process(
            target=_notify_failure_worker,
            args=(str(tmp_path), str(inc_path), str(notif_path), out_q),
        )
        for _ in range(3)
    ]
    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    for _ in workers:
        assert out_q.get(timeout=5) == "done"
    text = notif_path.read_text(encoding="utf-8")
    assert text.count("disk full") == 1


def test_failure_recovery_cycle(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    monkeypatch.setattr("app.api.notifications_store._notifications_path", lambda: notif_path)
    from app.core.operations.notification_service import notify_job_failure, notify_job_recovery

    notify_job_failure("backup", "disk full", "CRITICAL")
    notify_job_failure("backup", "disk full again", "CRITICAL")
    assert notif_path.read_text(encoding="utf-8").count("disk full") == 1
    notify_job_recovery("backup", "ok")
    notify_job_recovery("backup", "ok again")
    assert notif_path.read_text(encoding="utf-8").count("recovered") == 1
    notify_job_failure("backup", "new failure", "CRITICAL")
    assert notif_path.read_text(encoding="utf-8").count("new failure") == 1


def test_restart_reconstructs_open_incident(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    monkeypatch.setattr("app.api.notifications_store._notifications_path", lambda: notif_path)
    from app.core.operations.incident_store import get_open_incident, open_incident_if_absent
    from app.core.operations.notification_service import notify_job_failure

    opened = open_incident_if_absent("backup", "CRITICAL")
    notify_job_failure("backup", "disk full", "CRITICAL")
    assert get_open_incident("backup")["incident_id"] == opened["incident_id"]
    # Simulate restart by re-reading from disk only
    assert get_open_incident("backup") is not None
    notify_job_failure("backup", "still failing", "CRITICAL")
    assert notif_path.read_text(encoding="utf-8").count("disk full") == 1


def test_malformed_incident_persistence_fail_loud(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    inc_path.write_text("{not json\n", encoding="utf-8")
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    from app.core.operations.incident_store import IncidentStoreError, open_incident_if_absent

    with pytest.raises(IncidentStoreError):
        open_incident_if_absent("backup", "CRITICAL")
