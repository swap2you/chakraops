# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.6: Notifications JSONL retention (prune to last N lines)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.api.notifications_store import append_notification, load_notifications, _RETENTION_LINES


def test_retention_prunes_to_n_lines(tmp_path: Path) -> None:
    """After appending > N, file has N lines and last line is latest appended."""
    notif_path = tmp_path / "notifications.jsonl"
    n = 60  # use smaller N for fast test
    with patch("app.api.notifications_store._notifications_path", return_value=notif_path), \
         patch("app.api.notifications_store._RETENTION_LINES", n):
        notif_path.parent.mkdir(parents=True, exist_ok=True)
        for i in range(n + 10):
            append_notification("INFO", "TEST", f"message_{i}", details={"i": i})
        lines = notif_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == n
        last = lines[-1]
        assert f"message_{n + 9}" in last
