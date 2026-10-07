# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 notification incident correlation tests."""

from __future__ import annotations

from unittest.mock import patch


def test_failure_recovery_new_failure_cycle(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    monkeypatch.setattr("app.api.notifications_store._notifications_path", lambda: notif_path)

    from app.core.operations.notification_service import notify_job_failure, notify_job_recovery

    notify_job_failure("backup", "disk full", "CRITICAL")
    notify_job_failure("backup", "disk full", "CRITICAL")
    text1 = notif_path.read_text(encoding="utf-8")
    assert text1.count("disk full") == 1

    notify_job_recovery("backup", "ok")
    notify_job_recovery("backup", "ok")
    text2 = notif_path.read_text(encoding="utf-8")
    assert text2.count("recovered") == 1

    notify_job_failure("backup", "disk full again", "CRITICAL")
    assert notif_path.read_text(encoding="utf-8").count("disk full again") == 1


def test_incident_key_stable(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    from app.core.operations.incident_store import get_open_incident, open_incident_if_absent

    i1 = open_incident_if_absent("backup", "CRITICAL")["incident_id"]
    i2 = open_incident_if_absent("backup", "CRITICAL")["incident_id"]
    assert i1 == i2
    assert get_open_incident("backup")["incident_id"] == i1
