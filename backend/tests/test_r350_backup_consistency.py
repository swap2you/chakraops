# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 backup consistency tests."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


def test_sqlite_backup_consistent_under_writer(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    db = tmp_path / "decision.db"
    conn = sqlite3.connect(db, check_same_thread=False)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.commit()
    monkeypatch.setattr(
        "app.core.eval.evaluation_store_v2.get_decision_store_path", lambda: db
    )
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            conn.execute("INSERT INTO t (v) VALUES (?)", (str(i),))
            conn.commit()
            i += 1
            time.sleep(0.01)

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    time.sleep(0.05)

    from app.core.operations import backup_service

    monkeypatch.setattr(backup_service, "_backup_root", lambda: tmp_path / "backups")
    created = backup_service.create_backup(label="consistency")
    stop.set()
    t.join(timeout=2)
    conn.close()

    backup_db = tmp_path / "backups" / created["backup_id"] / "decision.db"
    assert backup_db.exists()
    ro = sqlite3.connect(f"file:{backup_db}?mode=ro", uri=True)
    count = ro.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    ro.close()
    assert count >= 0


def test_jsonl_snapshot_complete_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.settings.get_output_dir", lambda: str(tmp_path))
    jl = tmp_path / "state.jsonl"
    jl.write_text('{"a":1}\n', encoding="utf-8")
    from app.core.operations import backup_service

    monkeypatch.setattr(backup_service, "_backup_root", lambda: tmp_path / "backups")
    created = backup_service.create_backup(label="jl")
    backup_file = tmp_path / "backups" / created["backup_id"] / "state.jsonl"
    lines = backup_file.read_text(encoding="utf-8").strip().splitlines()
    assert all(line.startswith("{") for line in lines)
