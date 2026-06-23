# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R35.0 startup script static checks."""

from __future__ import annotations

from pathlib import Path


def test_startup_scripts_exist_and_reference_correct_path():
    root = Path(__file__).resolve().parents[2]
    start = root / "scripts" / "start_chakraops.ps1"
    stop = root / "scripts" / "stop_chakraops.ps1"
    assert start.exists()
    assert stop.exists()
    text = start.read_text(encoding="utf-8")
    assert "ChakraOps-dev" in text
    assert "ChakraOps\\chakraops" not in text.replace("ChakraOps-dev", "")
