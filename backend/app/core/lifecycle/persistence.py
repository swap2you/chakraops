# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2C: Lifecycle log persistence — out/lifecycle/lifecycle_log.jsonl."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _get_lifecycle_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "lifecycle"


def _ensure_lifecycle_dir() -> Path:
    p = _get_lifecycle_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _lifecycle_log_path() -> Path:
    return _ensure_lifecycle_dir() / "lifecycle_log.jsonl"


def append_lifecycle_entry(entry: Dict[str, Any]) -> None:
    """Append one lifecycle log entry (position_id, symbol, lifecycle_state, action, reason, triggered_at, eval_run_id)."""
    path = _lifecycle_log_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_recent_lifecycle_entries(limit: int = 100) -> List[Dict[str, Any]]:
    """Return most recent lifecycle log entries (for API/UI). Newest first."""
    path = _lifecycle_log_path()
    if not path.exists():
        return []
    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
    except Exception as e:
        logger.warning("[LIFECYCLE] Failed to read log: %s", e)
        return []
    result = []
    for line in reversed(lines[-limit:]):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return result[:limit]
