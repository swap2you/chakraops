# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.9: Execution discipline — execution log store, EOD mark-done block when NEW notifications, override, no FAIL_/WARN_."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_execution_log_write_and_list() -> None:
    """Execution log append and list work with temp DATA_DIR."""
    from app.core.ops.execution_log_store_r269 import (
        set_execution_log_db_path,
        reset_execution_log_db_path,
        init_execution_log_db,
        execution_log_append,
        execution_log_list,
        EVENT_MARK_DONE,
        EVENT_SKIP_JOURNAL,
        EVENT_EOD_OVERRIDE,
    )

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "exec_log.db"
        set_execution_log_db_path(db)
        init_execution_log_db()
        try:
            r1 = execution_log_append(EVENT_SKIP_JOURNAL, symbol="SPY", strategy="CSP", action="OPEN", ticket_id="t1", reason="Skipped for test")
            assert r1.get("event_type") == EVENT_SKIP_JOURNAL
            assert r1.get("symbol") == "SPY"
            assert r1.get("reason") == "Skipped for test"
            r2 = execution_log_append(EVENT_MARK_DONE, symbol="SPY", strategy="CSP", action="OPEN", ticket_id="t1")
            assert r2.get("event_type") == EVENT_MARK_DONE
            r3 = execution_log_append(EVENT_EOD_OVERRIDE, reason="Override test")
            assert r3.get("event_type") == EVENT_EOD_OVERRIDE
            rows = execution_log_list(limit=10)
            assert len(rows) >= 3
            rows_by_date = execution_log_list(date="2099-01-01", limit=10)
            assert len(rows_by_date) == 0
        finally:
            reset_execution_log_db_path()


def test_execution_log_api_post_and_get() -> None:
    """POST /api/ui/ops/execution-log and GET with date param."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.execution_log_store_r269 import set_execution_log_db_path, reset_execution_log_db_path, init_execution_log_db

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "exec_log_api.db"
        set_execution_log_db_path(db)
        init_execution_log_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post(
                    "/api/ui/ops/execution-log",
                    json={"event_type": "SKIP_JOURNAL", "symbol": "AAPL", "strategy": "CSP", "reason": "Test reason"},
                )
                assert r.status_code == 200
                data = r.json()
                assert data.get("status") == "OK"
                assert data.get("row", {}).get("event_type") == "SKIP_JOURNAL"
                r2 = client.get("/api/ui/ops/execution-log")
                assert r2.status_code == 200
                assert "rows" in r2.json()
                r3 = client.get("/api/ui/ops/execution-log?date=2099-01-01")
                assert r3.status_code == 200
        finally:
            reset_execution_log_db_path()


def test_eod_mark_done_409_when_new_notifications() -> None:
    """EOD mark-done returns 409 when NEW notifications exist and no override_reason."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.checklist_store_r264 import set_checklist_db_path, reset_checklist_db_path, init_checklist_db

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "checklist.db"
        set_checklist_db_path(db)
        init_checklist_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                with patch("app.api.notifications_store.get_notifications_health", return_value={"count_new": 2, "count_acked": 0, "count_archived": 0}):
                    client = TestClient(app)
                    r = client.post(
                        "/api/ui/ops/checklist/mark-done",
                        json={"kind": "EOD", "key": "2026-02-27"},
                    )
                    assert r.status_code == 409
                    assert "NEW" in (r.json().get("detail") or "")
        finally:
            reset_checklist_db_path()


def test_eod_mark_done_allows_with_override_reason_and_writes_log() -> None:
    """EOD mark-done with override_reason writes EOD_OVERRIDE to execution_log and returns 200."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.checklist_store_r264 import set_checklist_db_path, reset_checklist_db_path, init_checklist_db, checklist_get, STATUS_DONE
    from app.core.ops.execution_log_store_r269 import (
        set_execution_log_db_path,
        reset_execution_log_db_path,
        init_execution_log_db,
        execution_log_list,
        EVENT_EOD_OVERRIDE,
    )

    with tempfile.TemporaryDirectory() as tmp:
        cdb = Path(tmp) / "checklist.db"
        edb = Path(tmp) / "exec_log.db"
        set_checklist_db_path(cdb)
        set_execution_log_db_path(edb)
        init_checklist_db()
        init_execution_log_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                with patch("app.api.notifications_store.get_notifications_health", return_value={"count_new": 1, "count_acked": 0, "count_archived": 0}):
                    client = TestClient(app)
                    r = client.post(
                        "/api/ui/ops/checklist/mark-done",
                        json={"kind": "EOD", "key": "2026-02-28", "override_reason": "Inbox cleared manually"},
                    )
                    assert r.status_code == 200
                    assert r.json().get("status") == "OK"
                    row = checklist_get("EOD", "2026-02-28")
                    assert row and row.get("status") == STATUS_DONE
                    logs = execution_log_list(limit=5)
                    eod_overrides = [x for x in logs if x.get("event_type") == EVENT_EOD_OVERRIDE]
                    assert len(eod_overrides) >= 1
                    assert eod_overrides[0].get("reason") == "Inbox cleared manually"
        finally:
            reset_checklist_db_path()
            reset_execution_log_db_path()


def test_execution_log_and_eod_api_no_fail_warn_in_json() -> None:
    """Execution-log and mark-done API responses must not contain FAIL_ or WARN_ substrings."""
    from fastapi.testclient import TestClient
    from app.api.server import app
    from app.core.ops.checklist_store_r264 import set_checklist_db_path, reset_checklist_db_path, init_checklist_db
    from app.core.ops.execution_log_store_r269 import set_execution_log_db_path, reset_execution_log_db_path, init_execution_log_db

    with tempfile.TemporaryDirectory() as tmp:
        set_checklist_db_path(Path(tmp) / "cl.db")
        set_execution_log_db_path(Path(tmp) / "el.db")
        init_checklist_db()
        init_execution_log_db()
        try:
            with patch("app.api.ui_routes._require_ui_key"):
                client = TestClient(app)
                r = client.post("/api/ui/ops/execution-log", json={"event_type": "MARK_DONE", "symbol": "X"})
                assert r.status_code == 200
                assert "FAIL_" not in json.dumps(r.json())
                assert "WARN_" not in json.dumps(r.json())
                r2 = client.get("/api/ui/ops/execution-log")
                assert r2.status_code == 200
                assert "FAIL_" not in json.dumps(r2.json())
                assert "WARN_" not in json.dumps(r2.json())
                with patch("app.api.notifications_store.get_notifications_health", return_value={"count_new": 0}):
                    r3 = client.post("/api/ui/ops/checklist/mark-done", json={"kind": "EOD", "key": "2026-03-01"})
                    assert r3.status_code == 200
                    assert "FAIL_" not in json.dumps(r3.json())
                    assert "WARN_" not in json.dumps(r3.json())
        finally:
            reset_checklist_db_path()
            reset_execution_log_db_path()
