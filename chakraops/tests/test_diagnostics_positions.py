# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.6: Positions sanity check — unique run_id, guaranteed cleanup, no pollution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.api.diagnostics import _run_positions_check


def test_positions_check_cleanup_on_exception(tmp_path: Path) -> None:
    """Failure after create: cleanup in finally runs; no unhandled exception."""
    pos_dir = tmp_path / "positions"
    pos_dir.mkdir()
    (pos_dir / "positions.json").write_text("[]")

    with patch("app.core.positions.store._get_positions_dir", return_value=pos_dir):
        with patch("app.core.positions.service.list_positions", side_effect=RuntimeError("Simulated failure")):
            result = _run_positions_check()
    assert result["check"] == "positions"
    assert result["status"] == "FAIL"
    # Cleanup in finally runs; no exception escapes


def test_positions_check_idempotent_no_accumulation(tmp_path: Path) -> None:
    """Repeated runs do not accumulate open DIAG_TEST positions."""
    from app.core.positions import store as pos_store

    pos_dir = tmp_path / "positions"
    pos_dir.mkdir()
    (pos_dir / "positions.json").write_text("[]")

    with patch("app.core.positions.store._get_positions_dir", return_value=pos_dir):
        r1 = _run_positions_check()
        r2 = _run_positions_check()

    assert r1["check"] == "positions"
    assert r2["check"] == "positions"
    all_pos = pos_store.list_positions(status=None, symbol="DIAG_TEST")
    open_diag = [p for p in all_pos if p.status in ("OPEN", "PARTIAL_EXIT")]
    assert len(open_diag) == 0
