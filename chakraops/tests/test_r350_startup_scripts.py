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
    start_text = start.read_text(encoding="utf-8")
    stop_text = stop.read_text(encoding="utf-8")
    assert "ChakraOps-dev" in start_text
    assert "ChakraOps\\chakraops" not in start_text.replace("ChakraOps-dev", "")
    assert "chakraops_common.ps1" in start_text
    assert "chakraops_common.ps1" in stop_text
    assert '-like "$StaleRoot' not in start_text
    assert "Initialize-ChakraOpsCheckout" in start_text
