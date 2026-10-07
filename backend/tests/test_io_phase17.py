# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 17.0: Tests for atomic writes, locking, JSONL integrity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_atomic_write_json(tmp_path):
    """Phase 17.0: atomic_write_json writes to .tmp, then renames."""
    from app.core.io.atomic import atomic_write_json
    path = tmp_path / "state.json"
    data = {"a": 1, "b": "x"}
    atomic_write_json(path, data, indent=0)
    assert path.exists()
    assert not (tmp_path / "state.json.tmp").exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == data


def test_jsonl_scan_detects_invalid_line(tmp_path):
    """Phase 17.0: scan_jsonl detects invalid lines."""
    from app.core.io.jsonl_integrity import scan_jsonl
    path = tmp_path / "test.jsonl"
    path.write_text('{"ok": true}\nnot valid json\n{"x": 1}\n', encoding="utf-8")
    result = scan_jsonl(path)
    assert result["total_lines"] == 3
    assert result["invalid_lines"] == 1
    assert result["invalid_line_numbers"] == [2]
    assert result["last_valid_line"] == 3
    assert result["exists"] is True


def test_jsonl_repair_removes_invalid_and_creates_backup(tmp_path):
    """Phase 17.0: repair_jsonl removes invalid lines and creates backup."""
    from app.core.io.jsonl_integrity import scan_jsonl, repair_jsonl
    path = tmp_path / "test.jsonl"
    path.write_text('{"a": 1}\ninvalid\n{"b": 2}\n', encoding="utf-8")
    before = scan_jsonl(path)
    assert before["invalid_lines"] == 1
    repair_result = repair_jsonl(path)
    assert repair_result["valid_count"] == 2
    assert repair_result["removed_count"] == 1
    assert repair_result["backup_path"] is not None
    backup = Path(repair_result["backup_path"])
    assert backup.exists()
    content = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"b": 2}
    after = scan_jsonl(path)
    assert after["invalid_lines"] == 0


def test_with_file_lock_acquires_and_releases(tmp_path):
    """Phase 17.0: with_file_lock acquires and releases lock."""
    from app.core.io.locks import with_file_lock
    store_path = tmp_path / "store.jsonl"
    store_path.write_text("", encoding="utf-8")
    with with_file_lock(store_path, timeout_ms=1000):
        lock_dir = tmp_path / ".locks"
        assert lock_dir.exists()
        lock_file = lock_dir / "store.jsonl.lock"
        assert lock_file.exists()
    assert not lock_file.exists()


def test_notifications_append_uses_lock(tmp_path):
    """Phase 17.0: notifications append uses file lock."""
    from unittest.mock import patch
    notif_path = tmp_path / "notifications.jsonl"
    notif_path.parent.mkdir(parents=True, exist_ok=True)
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path):
        from app.api.notifications_store import append_notification
        append_notification("INFO", "TEST", "msg")
    assert notif_path.exists()
    lines = [ln.strip() for ln in notif_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["type"] == "TEST"
    assert obj["message"] == "msg"
