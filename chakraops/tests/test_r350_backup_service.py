# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 backup service tests."""

from __future__ import annotations

from pathlib import Path


def test_backup_create_verify_restore_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAKRAOPS_OUTPUT_DIR", str(tmp_path))
    out = tmp_path
    (out / "state.jsonl").write_text('{"x":1}\n', encoding="utf-8")

    from app.core.operations import backup_service

    monkeypatch.setattr(backup_service, "_backup_root", lambda: out / "backups")

    created = backup_service.create_backup(label="test")
    verify = backup_service.verify_backup(created["backup_id"])
    assert verify["ok"] is True
    restored = backup_service.restore_to_temp(created["backup_id"], temp_root=out / "validate")
    assert restored["ok"] is True
    assert (out / "validate" / "manifest.json").exists()


def test_retention_cleanup_safe(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(12):
        d = root / f"backup_auto_{i:02d}"
        d.mkdir()
        (d / "manifest.json").write_text('{"files":[]}', encoding="utf-8")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    result = backup_service.cleanup_expired_backups(retain_count=10)
    assert len(result["removed"]) == 2
    assert len(list(root.iterdir())) == 10
