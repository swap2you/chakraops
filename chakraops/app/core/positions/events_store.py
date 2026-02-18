# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 13.0: Position lifecycle events — append-only audit trail."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_RETENTION_LINES = 10000

EVENT_TYPES = frozenset({"OPEN", "FILL", "ADJUST", "CLOSE", "ABORT", "NOTE"})


def _events_path() -> Path:
    try:
        from app.core.positions.store import _get_positions_dir
        base = _get_positions_dir()
    except Exception:
        base = Path("out") / "positions"
    base.mkdir(parents=True, exist_ok=True)
    return base / "positions_events.jsonl"


def _prune_if_needed(path: Path) -> None:
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if len(lines) <= _RETENTION_LINES:
        return
    kept = lines[-_RETENTION_LINES:]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="positions_events.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for ln in kept:
                f.write(ln + "\n")
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise


def append_event(
    position_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    at_utc: Optional[str] = None,
) -> str:
    """Append a position lifecycle event. Returns event_id."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"event_type must be one of {EVENT_TYPES}")
    event_id = str(uuid.uuid4())
    now = at_utc or datetime.now(timezone.utc).isoformat()
    record = {
        "event_id": event_id,
        "position_id": position_id,
        "type": event_type,
        "at_utc": now,
        "payload": payload or {},
    }
    path = _events_path()
    line = json.dumps(record, default=str)
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        _prune_if_needed(path)
    logger.debug("[POSITIONS_EVENTS] Appended %s for %s", event_type, position_id)
    return event_id


def load_events_for_position(position_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Load events for a position in chronological order (oldest first)."""
    path = _events_path()
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with _LOCK:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if rec.get("position_id") == position_id:
                        events.append(rec)
                except (json.JSONDecodeError, TypeError):
                    continue
    # Return last N if over limit (most recent tail)
    if len(events) > limit:
        events = events[-limit:]
    return events
