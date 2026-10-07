# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.4: Ops checklists — mark done, reminder dedupe, weekly summary, no FAIL_/WARN_ in API."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_ops_checklist_mark_done_persists_and_fetch_returns_done() -> None:
    """Mark done persists; GET returns DONE."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.checklist_store_r264 import (
        init_checklist_db,
        set_checklist_db_path,
        reset_checklist_db_path,
        checklist_get,
        STATUS_DONE,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "checklist.db"
        set_checklist_db_path(db)
        init_checklist_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/ops/checklist/mark-done",
                    json={"kind": "EOD", "key": "2026-02-27"},
                )
                assert r.status_code == 200
                data = r.json()
                assert data.get("status") == "OK"
                assert data.get("row", {}).get("status") == STATUS_DONE
                assert data["row"].get("key") == "2026-02-27"
                r2 = client.get("/api/ui/ops/checklist?kind=EOD&key=2026-02-27")
                assert r2.status_code == 200
                row = r2.json().get("row") or {}
                assert row.get("status") == STATUS_DONE
        finally:
            reset_checklist_db_path()


def test_ops_checklist_api_no_fail_warn_in_json() -> None:
    """Checklist and eod-summary responses must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        for path in [
            "/api/ui/ops/checklist?kind=EOD&key=2026-02-27",
            "/api/ui/ops/eod-summary?date=2026-02-27",
            "/api/ui/ops/weekly-summary?week=2026-09",
        ]:
            r = client.get(path)
            assert r.status_code == 200, path
            raw = json.dumps(r.json())
            assert "FAIL_" not in raw, path
            assert "WARN_" not in raw, path


def test_reminder_emission_creates_notification_and_dedupes() -> None:
    """maybe_append_ops_checklist_reminder creates notification; second call with same key does not (dedupe)."""
    with tempfile.TemporaryDirectory() as tmp:
        notif_path = Path(tmp) / "notifications.jsonl"
        with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
            from app.api.notifications_store import (
                load_notifications,
                maybe_append_ops_checklist_reminder,
                OPS_EOD_CHECKLIST_REMINDER,
            )
            key = "2026-02-27-r264-test"
            first = maybe_append_ops_checklist_reminder(OPS_EOD_CHECKLIST_REMINDER, key)
            assert first is True
            recent = load_notifications(limit=50, state_filter=None)
            found = [n for n in recent if n.get("type") == OPS_EOD_CHECKLIST_REMINDER and (n.get("details") or {}).get("key") == key]
            assert len(found) >= 1
            second = maybe_append_ops_checklist_reminder(OPS_EOD_CHECKLIST_REMINDER, key)
            assert second is False
            recent2 = load_notifications(limit=50, state_filter=None)
            found2 = [n for n in recent2 if n.get("type") == OPS_EOD_CHECKLIST_REMINDER and (n.get("details") or {}).get("key") == key]
            assert len(found2) == len(found)


def test_weekly_summary_aggregates_from_journal_deterministically() -> None:
    """Weekly summary returns realized_pl_total and counts from journal for week range."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.journal.journal_store import (
        set_journal_db_path,
        reset_journal_db_path,
        init_journal_db,
        journal_create,
    )

    with tempfile.TemporaryDirectory() as tmp:
        jdb = Path(tmp) / "journal.db"
        set_journal_db_path(jdb)
        init_journal_db()
        try:
            journal_create("2026-02-24", "SPY", "CSP", "CLOSE", 1, premium=2.0, realized_pl=50.0)
            journal_create("2026-02-25", "QQQ", "SHARES", "SELL", 10, price=400.0, realized_pl=-20.0)
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.get("/api/ui/ops/weekly-summary?week=2026-09")
            assert r.status_code == 200
            data = r.json()
            assert "realized_pl_total" in data
            assert "trade_count" in data
            assert "winners" in data
            assert "losers" in data
            assert data["trade_count"] >= 2
            assert data["realized_pl_total"] == 30.0
        finally:
            reset_journal_db_path()
