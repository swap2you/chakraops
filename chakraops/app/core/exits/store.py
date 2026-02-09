# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Exit persistence. Phase 5: Multiple events per position (SCALE_OUT, FINAL_EXIT)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional

from app.core.exits.models import ExitRecord

logger = logging.getLogger(__name__)


def _get_exits_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "exits"


def _ensure_exits_dir() -> Path:
    p = _get_exits_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _exit_path(position_id: str) -> Path:
    safe = "".join(c for c in (position_id or "") if c.isalnum() or c in "-_")
    if not safe:
        raise ValueError("position_id required")
    return _ensure_exits_dir() / f"{safe}.json"


_LOCK = threading.Lock()


def load_exit_events(position_id: str) -> List[ExitRecord]:
    """
    Load all exit events for position. Phase 5: Supports multiple events (SCALE_OUT, FINAL_EXIT).
    Backward compat: single-object files migrated to events array with event_type=FINAL_EXIT.
    """
    path = _exit_path(position_id)
    if not path.exists():
        return []
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [ExitRecord.from_dict(d) for d in data]
            if isinstance(data, dict):
                # Phase 5 format: {"events": [...]}
                events = data.get("events")
                if isinstance(events, list):
                    return [ExitRecord.from_dict(d) for d in events]
                # Legacy: single object
                rec = ExitRecord.from_dict(data)
                rec.event_type = "FINAL_EXIT"
                return [rec]
            return []
        except Exception as e:
            logger.warning("[EXITS] Failed to load exit events for %s: %s", position_id, e)
            return []


def get_final_exit(position_id: str) -> Optional[ExitRecord]:
    """
    Return the FINAL_EXIT event for position. Full lifecycle (open → final exit) for derived metrics.
    If only one event exists (legacy), returns it.
    """
    events = load_exit_events(position_id)
    for e in reversed(events):
        if e.event_type == "FINAL_EXIT":
            return e
    return events[-1] if events else None


def load_exit(position_id: str) -> Optional[ExitRecord]:
    """Legacy: returns final exit (or single exit). Use get_final_exit for clarity."""
    return get_final_exit(position_id)


def save_exit(record: ExitRecord) -> ExitRecord:
    """Append exit event. Phase 5: Supports SCALE_OUT and FINAL_EXIT."""
    path = _exit_path(record.position_id)
    _ensure_exits_dir()
    events = load_exit_events(record.position_id)
    events.append(record)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"events": [e.to_dict() for e in events]}, f, indent=2)
    logger.info("[EXITS] Saved exit event %s for %s", record.event_type, record.position_id)
    return record


def list_exit_position_ids() -> list[str]:
    """Return list of position_ids that have exit records."""
    d = _get_exits_dir()
    if not d.exists():
        return []
    ids = []
    for p in d.glob("*.json"):
        ids.append(p.stem)
    return ids
