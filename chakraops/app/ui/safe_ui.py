# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Safe UI helpers: prevent crashes on None or missing keys (Phase 6.6)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, TypeVar

# Phase 6.6: UI_MODE = LIVE (default) | MOCK
UI_MODE_LIVE = "LIVE"
UI_MODE_MOCK = "MOCK"


def get_ui_mode() -> str:
    """Return UI_MODE from environment: LIVE (default) or MOCK."""
    return (os.environ.get("UI_MODE") or UI_MODE_LIVE).strip().upper() or UI_MODE_LIVE


def is_ui_mock() -> bool:
    """Return True when UI_MODE=MOCK."""
    return get_ui_mode() == UI_MODE_MOCK

T = TypeVar("T")


def ensure_dict(obj: Any) -> Dict[str, Any]:
    """Return obj if it is a dict, else {}."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    return {}


def ensure_list(obj: Any) -> List[Any]:
    """Return obj if it is a list, else []."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    return []


def safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely get nested key: safe_get(d, 'a', 'b') => d.get('a', {}).get('b', default)."""
    if obj is None and keys:
        return default
    current = obj
    for key in keys:
        current = ensure_dict(current).get(key)
        if current is None and key != keys[-1]:
            return default
    return default if current is None else current


def safe_int(val: Any, default: int = 0) -> int:
    """Return int(val) or default."""
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def safe_float(val: Any, default: float = 0.0) -> float:
    """Return float(val) or default."""
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_str(val: Any, default: str = "") -> str:
    """Return str(val) or default if None."""
    if val is None:
        return default
    return str(val)
