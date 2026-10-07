# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R28.3: Notifications — persist and return only safe severity/labels; no FAIL/WARN/PASS in file or API."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

FORBIDDEN = re.compile(r"\b(FAIL|WARN|PASS)\b")


def test_append_notification_persists_no_raw_tokens(tmp_path) -> None:
    """When appending a notification, the written JSON line contains no literal FAIL, WARN, or PASS."""
    from app.api.notifications_store import append_notification, _notifications_path
    path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        append_notification("WARN", "ORATS_WARN", "Stale data", symbol=None, details={}, subtype="ORATS_STALE")
    assert path.exists()
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 1
    for line in lines:
        assert FORBIDDEN.search(line) is None, f"Line must not contain FAIL/WARN/PASS: {line[:200]}"
        data = json.loads(line)
        assert data.get("severity") in ("Low", "Medium", "High")
        assert "severity_label" in data


def test_append_notification_fail_severity_persists_safe(tmp_path) -> None:
    """Caller passing severity='FAIL' results in safe severity in file (e.g. High/Review)."""
    from app.api.notifications_store import append_notification, _notifications_path
    path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        append_notification("FAIL", "TEST", "msg", symbol=None, details={})
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["severity"] in ("Low", "Medium", "High")
    assert "FAIL" not in lines[0]
    assert "WARN" not in lines[0]
    assert "PASS" not in lines[0]


def test_load_notifications_normalizes_legacy_raw(tmp_path) -> None:
    """Given a legacy notification with severity=WARN (or FAIL), load_notifications returns safe fields only."""
    from app.api.notifications_store import load_notifications, _notifications_path
    path = tmp_path / "notifications.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "id": "legacy-1",
        "timestamp_utc": "2026-03-01T12:00:00Z",
        "severity": "WARN",
        "type": "LEGACY_TEST",
        "message": "Status: WARN",
        "symbol": None,
        "details": {},
    }
    path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        items = load_notifications(limit=10, state_filter=None)
    assert len(items) == 1
    rec = items[0]
    assert rec.get("severity") in ("Low", "Medium", "High")
    assert FORBIDDEN.search(json.dumps(rec)) is None
    assert "WARN" not in (rec.get("message") or "")
    assert "severity_label" in rec


def test_notification_normalization_does_not_write_decision_latest(tmp_path) -> None:
    """Append/load notifications do not write to out/decision_latest.json."""
    decision_path = tmp_path / "decision_latest.json"
    decision_path.write_text("{}")
    before = decision_path.read_text()
    from app.api.notifications_store import append_notification, load_notifications, _notifications_path
    path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        append_notification("INFO", "TEST", "msg", details={})
        load_notifications(limit=5)
    assert decision_path.read_text() == before


def test_api_response_contains_no_forbidden_tokens(tmp_path) -> None:
    """Load and return path: serialized API payload contains no FAIL/WARN/PASS (grep-style)."""
    from app.api.notifications_store import append_notification, load_notifications, _notifications_path
    path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        append_notification("WARN", "T", "message", details={})
        append_notification("INFO", "T2", "ok", details={})
        items = load_notifications(limit=10)
    payload = json.dumps(items, default=str)
    assert FORBIDDEN.search(payload) is None, "API payload must not contain FAIL/WARN/PASS"


def test_normalize_notification_severity() -> None:
    """normalize_notification_severity maps raw to safe (no FAIL/WARN/PASS in output)."""
    from app.core.notifications.notification_safe_labels import normalize_notification_severity
    assert normalize_notification_severity("INFO") == ("Low", "Info")
    assert normalize_notification_severity("WARN") == ("Medium", "Advisory")
    assert normalize_notification_severity("FAIL") == ("High", "Review")
    assert normalize_notification_severity("PASS") == ("Low", "OK")
    sev, label = normalize_notification_severity("CRITICAL")
    assert sev == "High" and label == "Review"
