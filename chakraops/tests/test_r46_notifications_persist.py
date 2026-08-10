# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R46 — notifications persistence regression (reload from jsonl)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


def test_r46_notification_persists_across_reload(tmp_path: Path) -> None:
    """Appended notifications remain on disk and readable after a simulated restart."""
    from app.api.notifications_store import append_notification

    path = tmp_path / "notifications.jsonl"
    with patch("app.api.notifications_store._notifications_path", return_value=path):
        append_notification("Medium", "R46_TEST", "persisted", symbol="SPY", details={"k": 1})
        assert path.exists()
        # Simulate restart: re-open path and parse (store is append-only jsonl)
        raw = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert any(r.get("message") == "persisted" and r.get("type") == "R46_TEST" for r in raw)
        assert all("severity" in r for r in raw)
        # Second append must not wipe prior rows
        append_notification("Low", "R46_TEST_2", "also persisted", symbol=None, details={})
        raw2 = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(raw2) >= 2
        assert any(r.get("message") == "persisted" for r in raw2)
        assert any(r.get("message") == "also persisted" for r in raw2)
