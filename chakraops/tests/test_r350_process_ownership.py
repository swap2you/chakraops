# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 process ownership tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_write_read_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.core.operations.process_ownership.ownership_path",
        lambda: tmp_path / "process_ownership.json",
    )
    from app.core.operations.process_ownership import (
        clear_record,
        read_record,
        validate_repo_root,
        write_record,
        REPO_ROOT_EXPECTED,
    )

    validate_repo_root(REPO_ROOT_EXPECTED)
    with pytest.raises(ValueError, match="stale"):
        validate_repo_root(r"C:\Development\Workspace\ChakraOps")

    rec = write_record(
        backend_pid=111,
        frontend_pid=222,
        repo_root=REPO_ROOT_EXPECTED,
        backend_cmd="uvicorn",
        frontend_cmd="npm",
    )
    assert read_record()["backend_pid"] == 111
    clear_record()
    assert read_record() is None


def test_stop_script_refuses_stale_paths():
    root = Path(__file__).resolve().parents[2]
    stop = root / "scripts" / "stop_chakraops.ps1"
    text = stop.read_text(encoding="utf-8")
    assert "repo_root mismatch" in text.lower() or "Refusing" in text
    assert "ChakraOps-dev" in text
