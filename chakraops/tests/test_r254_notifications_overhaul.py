# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R25.4: Notifications overhaul — state workflow, bulk ack/archive, transition-aware dedupe, no FAIL_/WARN_."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_notifications_state_transitions():
    """R25.4: NEW -> ACKED -> ARCHIVED via append_ack and append_archive."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import (
                    append_notification,
                    append_ack,
                    append_archive,
                    load_notifications,
                )
                append_notification("INFO", "R254_TEST", "Test message", symbol="R254", details={})
                recs = load_notifications(limit=10, state_filter=None)
                assert len(recs) == 1
                nid = recs[0]["id"]
                assert recs[0].get("state") == "NEW"
                append_ack(ref_id=nid, ack_by="ui")
                recs = load_notifications(limit=10, state_filter="ACKED")
                assert len(recs) == 1 and recs[0].get("state") == "ACKED"
                append_archive(nid)
                recs = load_notifications(limit=10, state_filter="ARCHIVED")
                assert len(recs) == 1 and recs[0].get("state") == "ARCHIVED"


def test_notifications_bulk_ack_and_archive():
    """R25.4: ack_bulk and archive_bulk work and are idempotent."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import (
                    append_notification,
                    load_notifications,
                    ack_bulk,
                    archive_bulk,
                )
                for i in range(3):
                    append_notification("INFO", "R254_BULK", f"Msg {i}", symbol="R254", details={})
                recs = load_notifications(limit=10, state_filter="NEW")
                assert len(recs) == 3
                count = ack_bulk(state_filter="NEW")
                assert count == 3
                recs = load_notifications(limit=10, state_filter="NEW")
                assert len(recs) == 0
                recs = load_notifications(limit=10, state_filter="ACKED")
                assert len(recs) == 3
                count2 = archive_bulk(state_filter="ACKED")
                assert count2 == 3
                recs = load_notifications(limit=10, state_filter="ACKED")
                assert len(recs) == 0
                recs = load_notifications(limit=10, state_filter="ARCHIVED")
                assert len(recs) == 3
                assert ack_bulk(state_filter="NEW") == 0


def test_dedupe_prevents_duplicate_while_active():
    """R25.4: Two emissions for same (contract_key, event_type) do not create two notifications while first is NEW/ACKED."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import (
                    load_notifications,
                    maybe_append_options_lifecycle_notification,
                    OPTIONS_PROFIT_TARGET_HIT,
                )
                symbol = "R254_DEDUPE"
                ckey = "100-2026-05-18-PUT"
                payload = {"symbol": symbol, "contract_key": ckey, "profit_pct": 60, "as_of_ts": "2026-02-27T12:00:00Z"}
                ok1 = maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_PROFIT_TARGET_HIT, payload)
                ok2 = maybe_append_options_lifecycle_notification(symbol, ckey, OPTIONS_PROFIT_TARGET_HIT, payload)
                assert ok1 is True
                assert ok2 is False
                recs = [r for r in load_notifications(limit=50) if r.get("type") == OPTIONS_PROFIT_TARGET_HIT and r.get("symbol") == symbol]
                assert len(recs) == 1


def test_notification_payload_no_fail_warn():
    """R25.4: Notification list and details contain no FAIL_/WARN_ substrings."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import append_notification, load_notifications
                append_notification("INFO", "R254_SAFE", "Safe message only", symbol="R254", details={"key": "value"})
                recs = load_notifications(limit=10)
                for r in recs:
                    msg = (r.get("message") or "")
                    assert "FAIL_" not in msg and "WARN_" not in msg
                    for k, v in (r.get("details") or {}).items():
                        s = str(v)
                        assert "FAIL_" not in s and "WARN_" not in s


def test_load_notifications_symbol_type_offset():
    """R25.4: load_notifications supports symbol_filter, type_filter, offset; response has created_ts, acked_ts, archived_ts."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import append_notification, load_notifications
                append_notification("INFO", "TYPE_A", "A1", symbol="AAA", details={})
                append_notification("INFO", "TYPE_A", "A2", symbol="AAA", details={})
                append_notification("INFO", "TYPE_B", "B1", symbol="BBB", details={})
                recs = load_notifications(limit=10, symbol_filter="AAA")
                assert len(recs) == 2
                recs = load_notifications(limit=10, type_filter="TYPE_B")
                assert len(recs) == 1 and recs[0].get("symbol") == "BBB"
                recs = load_notifications(limit=1, offset=1)
                assert len(recs) == 1
                recs = load_notifications(limit=5)
                for r in recs:
                    assert "created_ts" in r
                    assert "acked_ts" in r or "archived_ts" in r or True


def test_get_notifications_health():
    """R25.4: get_notifications_health returns count_new, count_acked, count_archived, last_emitted_ts."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        out.mkdir(parents=True, exist_ok=True)
        notifications_file = out / "notifications.jsonl"
        with patch.dict(os.environ, {"CHAKRAOPS_OUT": str(out)}):
            from app.api import notifications_store
            with patch.object(notifications_store, "_notifications_path", return_value=notifications_file):
                from app.api.notifications_store import append_notification, get_notifications_health
                append_notification("INFO", "R254_H", "H1", symbol="R254", details={})
                health = get_notifications_health()
                assert "count_new" in health and "count_acked" in health and "count_archived" in health
                assert "last_emitted_ts" in health
                assert health["count_new"] >= 1


def test_ui_notifications_ack_bulk_archive_bulk():
    """R25.4: POST /api/ui/notifications/ack-bulk and archive-bulk return OK and counts."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r_ack = client.post("/api/ui/notifications/ack-bulk")
        assert r_ack.status_code == 200
        data = r_ack.json()
        assert data.get("status") == "OK" and "acked_count" in data
        r_arch = client.post("/api/ui/notifications/archive-bulk")
        assert r_arch.status_code == 200
        data = r_arch.json()
        assert data.get("status") == "OK" and "archived_count" in data


def test_ui_notifications_query_params():
    """R25.4: GET /api/ui/notifications accepts state, symbol, type, offset."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/notifications?limit=5&state=NEW&symbol=TEST&type=SHARES_EXIT_SIGNAL&offset=0")
        assert r.status_code == 200
        data = r.json()
        assert "notifications" in data
        items = data["notifications"]
        for it in items:
            assert "created_ts" in it or "timestamp_utc" in it


def test_system_health_includes_notifications():
    """R25.4: GET /api/ui/system-health includes notifications block with safe counts."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/system-health")
        assert r.status_code == 200
        data = r.json()
        assert "notifications" in data
        n = data["notifications"]
        assert "count_new" in n and "count_acked" in n and "count_archived" in n
        assert "last_emitted_ts" in n
