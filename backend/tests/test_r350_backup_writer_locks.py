# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 backup writer-lock coordination tests."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path


def test_writer_lock_mapping_includes_core_stores(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    from app.core.operations.backup_writer_locks import build_snapshot_targets

    targets = build_snapshot_targets(tmp_path)
    names = {t.source.name for t in targets}
    assert "job_runs.jsonl" in names
    assert "scheduler_occurrences.jsonl" in names
    assert "job_incidents.jsonl" in names


def _job_run_writer(coord: str, n: int, stop_path: str) -> None:
    import app.core.settings as settings

    settings.get_output_dir = lambda: coord  # type: ignore[method-assign]
    from app.core.operations.job_run_store import JobRunStore

    store = JobRunStore()
    i = 0
    while i < n and not Path(stop_path).exists():
        run = store.start_run(job_id="backup", trigger="test")
        store.finish_run(run["run_id"], state="SUCCEEDED")
        i += 1
        time.sleep(0.01)


def test_backup_snapshots_complete_job_runs_under_concurrent_writer(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    stop_flag = tmp_path / "stop"
    t = threading.Thread(
        target=_job_run_writer,
        args=(str(tmp_path), 50, str(stop_flag)),
        daemon=True,
    )
    t.start()
    time.sleep(0.05)

    from app.core.operations import backup_service

    monkeypatch.setattr(backup_service, "_backup_root", lambda: tmp_path / "backups")
    created = backup_service.create_backup(label="writer-lock")
    stop_flag.write_text("1", encoding="utf-8")
    t.join(timeout=5)

    backup_file = tmp_path / "backups" / created["backup_id"] / "job_runs.jsonl"
    assert backup_file.exists()
    for line in backup_file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)
    manifest = created["manifest"]
    entry = next(e for e in manifest["files"] if e["name"] == "job_runs.jsonl")
    assert entry["consistency"] == "writer_cross_process_lock_snapshot"


def test_manifest_records_writer_lock_coordination(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    jl = tmp_path / "job_incidents.jsonl"
    jl.write_text('{"event":"open","incident_id":"x","job_id":"backup"}\n', encoding="utf-8")
    from app.core.operations import backup_service

    monkeypatch.setattr(backup_service, "_backup_root", lambda: tmp_path / "backups")
    created = backup_service.create_backup(label="manifest")
    assert created["manifest"]["writer_lock_coordination"] is True
    assert "writer_lock_coordinated_snapshot" in created["manifest"]["snapshot_policy"]
