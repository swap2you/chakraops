# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Append-only history of weekly universe refreshes (R32.0).

Records each refresh run (week id, run timestamp, resulting symbols, change
sets, and reason codes) as a JSON line. This provides an auditable refresh
history without a database migration (forbidden in R32).

File-backed and watchdog-safe: appends create the parent directory and write a
single newline-terminated JSON record. Reads tolerate malformed trailing lines.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


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
        # Atomic append: read existing content, append the new record, then write
        # the whole file via temp + fsync + os.replace. This makes the history
        # mutation a single atomic replacement so an interruption can never leave
        # a torn trailing line, and pairs with the cross-process refresh lock.
        from app.core.universe.refresh_lock import atomic_write_text

        existing = ""
        if self._path.exists():
            try:
                existing = self._path.read_text(encoding="utf-8")
            except OSError:
                existing = ""
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
        """Return the most recent record, or None."""
        recent = self.read_recent(limit=1)
        return recent[0] if recent else None
