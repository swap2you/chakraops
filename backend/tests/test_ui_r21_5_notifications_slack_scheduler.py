# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R21.5: Notifications lifecycle (state, archive, delete, archive_all), Slack test, Scheduler skip reason, Force eval."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _get_app():
    from app.api.server import app
    return app


def test_notifications_state_and_filter(tmp_path):
    """Phase 21.5: Notifications have state/updated_at; list can filter by state."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    app = _get_app()
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.api.notifications_store import append_notification, load_notifications
        append_notification("WARN", "TEST", "msg1", details={})
        append_notification("INFO", "TEST", "msg2", details={})
        items = load_notifications(limit=10, state_filter=None)
        assert len(items) == 2
        for n in items:
            assert "state" in n
            assert n["state"] in ("NEW", "ACKED", "ARCHIVED", "DELETED")
            assert "updated_at" in n
        new_only = load_notifications(limit=10, state_filter="NEW")
        assert len(new_only) == 2
        assert all(n.get("state") == "NEW" for n in new_only)


def test_notifications_ack_archive_delete_archive_all(tmp_path):
    """Phase 21.5: Ack, archive, delete per-id; archive_all; list returns state."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    app = _get_app()
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.api.notifications_store import (
            append_notification,
            load_notifications,
            append_ack,
            append_archive,
            append_delete,
            archive_all,
        )
        append_notification("WARN", "T1", "m1", details={})
        append_notification("INFO", "T2", "m2", details={})
        items = load_notifications(limit=10)
        assert len(items) == 2
        n1_id = items[0]["id"]
        n2_id = items[1]["id"]
        # Ack first
        append_ack(n1_id, "ui")
        items_after_ack = load_notifications(limit=10)
        acked = [n for n in items_after_ack if n["id"] == n1_id]
        assert len(acked) == 1 and acked[0].get("state") == "ACKED"
        # Archive second
        append_archive(n2_id)
        items_after_arch = load_notifications(limit=10)
        arch = [n for n in items_after_arch if n["id"] == n2_id]
        assert len(arch) == 1 and arch[0].get("state") == "ARCHIVED"
        # Filter NEW: only none left (both acked/archived)
        new_list = load_notifications(limit=10, state_filter="NEW")
        assert len(new_list) == 0
        # Delete first (soft)
        append_delete(n1_id)
        all_list = load_notifications(limit=10)
        assert len(all_list) == 1  # DELETED excluded
        # Archive all (the remaining ACKED is already gone; add one NEW again via new notif)
        append_notification("WARN", "T3", "m3", details={})
        count = archive_all(limit=100)
        assert count >= 1
        after = load_notifications(limit=10, state_filter="ARCHIVED")
        assert len(after) >= 1


def test_ui_notifications_archive_and_delete_endpoints(tmp_path):
    """Phase 21.5: POST archive, DELETE delete, POST archive_all return OK and update state."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    app = _get_app()
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.api.notifications_store import append_notification, load_notifications
        append_notification("WARN", "TEST", "msg", details={})
        items = load_notifications(10)
        nid = items[0]["id"]
        client = TestClient(app)
        r_arch = client.post(f"/api/ui/notifications/{nid}/archive")
        assert r_arch.status_code == 200
        assert r_arch.json().get("status") == "OK"
        with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
            items2 = load_notifications(10)
            arch = [n for n in items2 if n["id"] == nid]
            assert len(arch) == 1 and arch[0].get("state") == "ARCHIVED"
        append_notification("INFO", "T2", "m2", details={})
        items3 = load_notifications(10)
        nid2 = [n["id"] for n in items3 if n.get("state") == "NEW"][0]
        r_del = client.delete(f"/api/ui/notifications/{nid2}")
        assert r_del.status_code == 200
        with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
            items4 = load_notifications(10)
            assert not any(n["id"] == nid2 for n in items4)
        r_all = client.post("/api/ui/notifications/archive_all")
        assert r_all.status_code == 200
        assert "archived_count" in r_all.json()


def test_ui_admin_slack_test_updates_status(tmp_path):
    """Phase 21.5: POST admin/slack/test sends (or fails) and updates Slack status record."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    slack_status_path = tmp_path / "slack_status.json"
    app = _get_app()
    with patch("app.core.alerts.slack_status._status_path", return_value=slack_status_path):
        with patch("app.core.alerts.slack_dispatcher.send_slack_message", return_value=True):
            client = TestClient(app)
            r = client.post("/api/ui/admin/slack/test")
            assert r.status_code == 200
            data = r.json()
            assert data.get("status") in ("OK", "error")
            assert "last_send_ok" in data or "message" in data
        from app.core.alerts.slack_status import get_slack_status
        status = get_slack_status()
        assert "last_send_at" in status or "last_any_send_at" in status
        assert "channels" in status
        assert "signals" in status["channels"]


def test_ui_admin_slack_test_per_channel(tmp_path):
    """R21.5.1: POST admin/slack/test?channel=critical updates that channel's status."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    slack_status_path = tmp_path / "slack_status.json"
    app = _get_app()
    with patch("app.core.alerts.slack_status._status_path", return_value=slack_status_path):
        with patch("app.core.alerts.slack_dispatcher.send_slack_message", return_value=True):
            with patch("app.core.alerts.slack_dispatcher.get_webhook_for_channel", return_value="https://hooks.slack.com/critical"):
                client = TestClient(app)
                r = client.post("/api/ui/admin/slack/test?channel=critical")
                assert r.status_code == 200
                data = r.json()
                assert data.get("channel") == "critical"
                assert data.get("ok") is True
                assert "updated_status" in data
                assert "channels" in data["updated_status"]
                assert "critical" in data["updated_status"]["channels"]
                assert data["updated_status"]["channels"]["critical"].get("last_send_ok") is True


def test_scheduler_status_includes_last_skip_reason():
    """Phase 21.5: get_scheduler_status returns last_skip_reason when scheduler skipped."""
    from app.api.server import get_scheduler_status
    status = get_scheduler_status()
    assert "last_skip_reason" in status


def test_scheduler_status_includes_r21_51_fields():
    """R21.5.1: get_scheduler_status returns last_duration_ms, last_run_ok, last_run_error, run_count_today."""
    from app.api.server import get_scheduler_status
    status = get_scheduler_status()
    assert "last_duration_ms" in status
    assert "last_run_ok" in status
    assert "last_run_error" in status
    assert "run_count_today" in status


def test_ui_system_health_includes_slack_and_scheduler_skip_reason():
    """Phase 21.5: GET system-health includes slack block and scheduler.last_skip_reason."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    client = TestClient(app)
    r = client.get("/api/ui/system-health")
    if r.status_code == 401:
        pytest.skip("UI key required")
    assert r.status_code == 200
    data = r.json()
    assert "scheduler" in data
    assert "last_skip_reason" in data["scheduler"]
    assert "slack" in data
    assert "last_send_at" in data["slack"] or "last_any_send_at" in data["slack"]
    assert "channels" in data["slack"]


def test_ui_system_health_scheduler_r21_51_fields():
    """R21.5.1: GET system-health scheduler block has last_duration_ms, last_run_ok, run_count_today."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    client = TestClient(app)
    r = client.get("/api/ui/system-health")
    if r.status_code == 401:
        pytest.skip("UI key required")
    assert r.status_code == 200
    sched = r.json().get("scheduler") or {}
    assert "last_duration_ms" in sched
    assert "last_run_ok" in sched
    assert "run_count_today" in sched


def test_ui_admin_evaluation_force_returns_forced():
    """Phase 21.5: POST admin/evaluation/force returns success and forced=True."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    app = _get_app()
    with patch("app.api.data_health.get_universe_symbols", return_value=[]):
        client = TestClient(app)
        r = client.post("/api/ui/admin/evaluation/force")
    if r.status_code == 401:
        pytest.skip("UI key required")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "OK"
    assert data.get("forced") is True
    assert "started" in data
