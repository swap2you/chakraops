# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 backup retention safety tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_backup(root: Path, name: str, *, created_at: str = "2026-06-01T00:00:00+00:00") -> Path:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"created_at": created_at, "files": []}),
        encoding="utf-8",
    )
    return d


def test_dry_run_performs_no_deletion(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(12):
        _make_backup(root, f"backup_auto_{i:02d}", created_at=f"2026-06-{i+1:02d}T00:00:00+00:00")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    result = backup_service.cleanup_expired_backups(retain_count=10, dry_run=True)
    assert result["dry_run"] is True
    assert len(result["would_remove"]) == 2
    assert result["removed"] == []
    assert len(list(root.iterdir())) == 12


def test_outside_root_path_rejected(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    outside = tmp_path / "outside_backup"
    _make_backup(outside, "backup_evil")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    monkeypatch.setattr(
        backup_service,
        "list_backups",
        lambda: [{"backup_id": "backup_evil", "path": str(outside / "backup_evil"), "created_at": "2026-01-01"}],
    )
    result = backup_service.cleanup_expired_backups(retain_count=0, dry_run=True)
    assert result["would_remove"] == []
    assert result["rejected"]
    assert result["rejected"][0]["reason"] == "outside backup root"


def test_backup_root_path_rejected(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    (root / "manifest.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    monkeypatch.setattr(
        backup_service,
        "list_backups",
        lambda: [{"backup_id": "root", "path": str(root), "created_at": "2026-01-01"}],
    )
    result = backup_service.cleanup_expired_backups(retain_count=0, dry_run=True)
    assert result["rejected"][0]["reason"] == "backup root itself"


def test_traversal_path_rejected(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    evil = root / ".." / "live.jsonl"
    evil.parent.mkdir(exist_ok=True)
    evil.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    monkeypatch.setattr(
        backup_service,
        "list_backups",
        lambda: [{"backup_id": "x", "path": str(evil), "created_at": "2026-01-01"}],
    )
    result = backup_service.cleanup_expired_backups(retain_count=0, dry_run=True)
    assert result["rejected"]
    assert result["rejected"][0]["reason"] == "outside backup root"


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink unsupported")
def test_escaping_symlink_rejected(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    _make_backup(outside, "real_backup")
    link = root / "link_backup"
    try:
        link.symlink_to(outside / "real_backup", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unsupported")
    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    monkeypatch.setattr(
        backup_service,
        "list_backups",
        lambda: [{"backup_id": "link_backup", "path": str(link), "created_at": "2026-01-01"}],
    )
    result = backup_service.cleanup_expired_backups(retain_count=0, dry_run=True)
    assert result["rejected"]
    assert "reparse" in result["rejected"][0]["reason"] or result["rejected"][0]["reason"] == "outside backup root"


def test_newest_backups_retained(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(5):
        _make_backup(root, f"b{i}", created_at=f"2026-06-0{i+1}T00:00:00+00:00")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    result = backup_service.cleanup_expired_backups(retain_count=3, dry_run=True)
    assert len(result["would_retain"]) == 3
    assert result["would_retain"] == ["b4", "b3", "b2"]


def test_confirmed_cleanup_deletes_eligible_only(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    for i in range(12):
        _make_backup(root, f"backup_{i:02d}", created_at=f"2026-06-{i+1:02d}T00:00:00+00:00")

    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    result = backup_service.cleanup_expired_backups(
        retain_count=10,
        dry_run=False,
        confirm=True,
        confirm_token=backup_service.CLEANUP_CONFIRM_TOKEN,
    )
    assert len(result["removed"]) == 2
    assert len(list(root.iterdir())) == 10


def test_destructive_requires_confirm_token(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    with pytest.raises(backup_service.BackupCleanupError):
        backup_service.cleanup_expired_backups(dry_run=False, confirm=True, confirm_token="wrong")


def test_repeated_cleanup_harmless(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    root = tmp_path / "backups"
    root.mkdir()
    _make_backup(root, "only_one")
    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    r1 = backup_service.cleanup_expired_backups(retain_count=10, dry_run=False, confirm=True, confirm_token=backup_service.CLEANUP_CONFIRM_TOKEN)
    r2 = backup_service.cleanup_expired_backups(retain_count=10, dry_run=False, confirm=True, confirm_token=backup_service.CLEANUP_CONFIRM_TOKEN)
    assert r1["removed"] == []
    assert r2["removed"] == []
    assert (root / "only_one").exists()


def test_live_state_unchanged(tmp_path, monkeypatch):
    from app.core.operations import backup_service

    out = tmp_path / "out"
    out.mkdir()
    live = out / "job_runs.jsonl"
    live.write_text('{"run":1}\n', encoding="utf-8")
    root = out / "backups"
    root.mkdir()
    _make_backup(root, "old", created_at="2026-01-01T00:00:00+00:00")

    monkeypatch.setenv("CHAKRAOPS_OUTPUT_DIR", str(out))
    monkeypatch.setattr(backup_service, "_backup_root", lambda: root)
    backup_service.cleanup_expired_backups(
        retain_count=0,
        dry_run=False,
        confirm=True,
        confirm_token=backup_service.CLEANUP_CONFIRM_TOKEN,
    )
    assert live.read_text(encoding="utf-8") == '{"run":1}\n'
