# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Append-only history of weekly universe refreshes (R32.0).

Records each refresh run (week id, run timestamp, resulting symbols, change
sets, and reason codes) as a JSON line. This provides an auditable refresh
history without a database migration (forbidden in R32).

File-backed and watchdog-safe: appends create the parent directory and write a
single newline-terminated JSON record. Transaction paths use strict reads so
corruption or unreadable history never masquerades as an empty history.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class RefreshHistoryError(RuntimeError):
    """Raised when refresh history cannot be read safely for a transaction."""


class RefreshHistoryCorruptionError(RefreshHistoryError):
    """Raised when refresh history contains malformed records."""


def _default_history_path() -> Path:
    repo = Path(__file__).resolve().parents[3]
    return repo / "artifacts" / "state" / "universe_refresh_history.jsonl"


class RefreshHistoryStore:
    """Append-only JSONL store of weekly universe refresh runs."""

    def __init__(self, path: Optional[Union[str, Path]] = None) -> None:
        self._path = Path(path) if path is not None else _default_history_path()

    @property
    def path(self) -> Path:
        return self._path

    def _read_existing_strict(self) -> str:
        """Read the full history file for append; fail loud on any problem."""
        if not self._path.exists():
            return ""
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError as e:
            raise RefreshHistoryError(
                f"unreadable refresh history at {self._path}: {e}"
            ) from e

    def _validate_existing_lines(self, text: str) -> None:
        """Ensure every non-empty line is valid JSON object (preserve file on failure)."""
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise RefreshHistoryCorruptionError(
                    f"malformed refresh history line {lineno} at {self._path}: {e}"
                ) from e
            if not isinstance(obj, dict):
                raise RefreshHistoryCorruptionError(
                    f"refresh history line {lineno} at {self._path} is not a JSON object"
                )

    def read_all_strict(self) -> List[Dict[str, Any]]:
        """Return all records in file order; raise on unreadable or corrupt history."""
        text = self._read_existing_strict()
        if not text.strip():
            return []
        self._validate_existing_lines(text)
        records: List[Dict[str, Any]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            obj = json.loads(stripped)
            if isinstance(obj, dict):
                records.append(obj)
        return records

    def append(
        self,
        *,
        week_id: str,
        symbols: List[str],
        reason_codes: List[str],
        added: Optional[List[str]] = None,
        removed: Optional[List[str]] = None,
        source: str = "weekly_refresh",
        run_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Append one refresh record and return it."""
        ts = run_at or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        record: Dict[str, Any] = {
            "run_at_utc": ts.astimezone(timezone.utc).isoformat(),
            "week_id": week_id,
            "source": source,
            "symbols": list(symbols),
            "count": len(symbols),
            "added": list(added or []),
            "removed": list(removed or []),
            "reason_codes": list(reason_codes),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        from app.core.universe.refresh_lock import atomic_write_text

        existing = self._read_existing_strict()
        if existing.strip():
            self._validate_existing_lines(existing)
        if existing and not existing.endswith("\n"):
            existing += "\n"
        atomic_write_text(self._path, existing + json.dumps(record, sort_keys=True) + "\n")
        return record

    def read_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent records (newest first), tolerating bad lines."""
        if not self._path.exists():
            return []
        records: List[Dict[str, Any]] = []
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        records.append(obj)
        except OSError:
            return []
        records.reverse()
        if limit is not None and limit >= 0:
            return records[:limit]
        return records

    def last(self) -> Optional[Dict[str, Any]]:
        """Return the most recent record for transaction/idempotency checks."""
        records = self.read_all_strict()
        return records[-1] if records else None
