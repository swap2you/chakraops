# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.6: Diagnostics history JSONL retention (prune to last N lines)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.api.diagnostics import _append_run, _diagnostics_history_path, _RETENTION_LINES


def test_diagnostics_retention_prunes(tmp_path: Path) -> None:
    """After appending > N runs, file has N lines."""
    hist_path = tmp_path / "diagnostics_history.jsonl"
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    n = 60  # use smaller N for fast test
    with patch("app.api.diagnostics._diagnostics_history_path", return_value=hist_path), \
         patch("app.api.diagnostics._RETENTION_LINES", n):
        for i in range(n + 10):
            _append_run({"timestamp_utc": f"2026-01-01T12:00:{i:02d}Z", "run": i})
        lines = [ln for ln in hist_path.read_text(encoding="utf-8").strip().split("\n") if ln.strip()]
        assert len(lines) == n
        last = json.loads(lines[-1])
        assert last["run"] == n + 9
