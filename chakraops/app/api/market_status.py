# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 10: Market status persistence — last_market_check, evaluation_attempted, evaluation_emitted, skip_reason."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from app.core.settings import get_output_dir
except ImportError:
    def get_output_dir() -> str:
        return "out"


def _status_path() -> Path:
    return Path(get_output_dir()) / "market_status.json"


def read_market_status() -> Dict[str, Any]:
    """Read market status from market_status.json. Returns defaults if missing."""
    p = _status_path()
    defaults = {
        "last_market_check": None,
        "last_evaluated_at": None,
        "evaluation_attempted": False,
        "evaluation_emitted": False,
        "skip_reason": None,
        "source_mode": "DRY_RUN",
    }
    if not p.exists():
        return defaults
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        for k in defaults:
            if k not in data:
                data[k] = defaults[k]
        return data
    except Exception:
        return defaults


def write_market_status(
    *,
    last_market_check: Optional[str] = None,
    last_evaluated_at: Optional[str] = None,
    evaluation_attempted: bool = False,
    evaluation_emitted: bool = False,
    skip_reason: Optional[str] = None,
    source_mode: str = "DRY_RUN",
) -> None:
    """Update market status (merge with existing). Pass only fields to update."""
    p = _status_path()
    current = read_market_status()
    if last_market_check is not None:
        current["last_market_check"] = last_market_check
    if last_evaluated_at is not None:
        current["last_evaluated_at"] = last_evaluated_at
    if evaluation_attempted is not None:
        current["evaluation_attempted"] = evaluation_attempted
    if evaluation_emitted is not None:
        current["evaluation_emitted"] = evaluation_emitted
    if skip_reason is not None:
        current["skip_reason"] = skip_reason
    if source_mode is not None:
        current["source_mode"] = source_mode
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)


def update_heartbeat() -> None:
    """Set last_market_check to now (ISO)."""
    write_market_status(last_market_check=datetime.now(timezone.utc).isoformat())
