# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.7: File-backed state for universe tier scheduling.

Watchdog-safe: creates path if missing, atomic writes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union


def _default_state_path() -> Path:
    repo = Path(__file__).resolve().parents[3]
    return repo / "artifacts" / "state" / "universe_state.json"


class UniverseStateStore:
    """
    Persists tier_last_run_utc and tier_cursor for round-robin scheduling.
    Creates state file if missing; uses atomic write (write to temp, then rename).
    """

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(path) if path is not None else _default_state_path()

    def load(self) -> Dict[str, Any]:
        """Load state; returns defaults if file missing or invalid."""
        if not self._path.exists():
            return {"tier_last_run_utc": {}, "tier_cursor": {}}
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {"tier_last_run_utc": {}, "tier_cursor": {}}
        if not isinstance(data, dict):
            return {"tier_last_run_utc": {}, "tier_cursor": {}}
        return {
            "tier_last_run_utc": dict(data.get("tier_last_run_utc") or {}),
            "tier_cursor": dict(data.get("tier_cursor") or {}),
        }

    def save(self, state: Dict[str, Any]) -> None:
        """Persist state with atomic write."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tier_last_run_utc": dict(state.get("tier_last_run_utc") or {}),
            "tier_cursor": dict(state.get("tier_cursor") or {}),
        }
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent,
            prefix="universe_state_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=0)
            os.replace(tmp, self._path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
