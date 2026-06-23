# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 notification dedupe tests."""

from __future__ import annotations

from unittest.mock import patch


def test_notification_dedupe(tmp_path):
    notif_path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.core.operations.notification_service import notify_job_failure

        notify_job_failure("backup", "disk full", "CRITICAL")
        notify_job_failure("backup", "disk full", "CRITICAL")
        text = notif_path.read_text(encoding="utf-8")
        assert text.count("disk full") == 1


def test_recovery_without_open_incident_is_noop(tmp_path, monkeypatch):
    inc_path = tmp_path / "incidents.jsonl"
    notif_path = tmp_path / "notifications.jsonl"
    monkeypatch.setattr("app.core.operations.incident_store._path", lambda: inc_path)
    monkeypatch.setattr("app.api.notifications_store._notifications_path", lambda: notif_path)
    from app.core.operations.notification_service import notify_job_recovery

    notify_job_recovery("backup", "run completed")
    assert not notif_path.exists() or notif_path.read_text(encoding="utf-8").strip() == ""
