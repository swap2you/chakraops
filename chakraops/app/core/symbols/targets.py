# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2B: Stock entry/exit targets — JSON persistence per symbol."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _get_targets_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "symbols"


def _ensure_targets_dir() -> Path:
    p = _get_targets_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _targets_path(symbol: str) -> Path:
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("Symbol required")
    return _ensure_targets_dir() / f"{sym}_targets.json"


_LOCK = threading.Lock()


def get_targets(symbol: str) -> Dict[str, Any]:
    """Get stored targets for symbol. Returns defaults if none stored."""
    path = _targets_path(symbol)
    if not path.exists():
        return {
            "symbol": symbol.strip().upper(),
            "entry_low": None,
            "entry_high": None,
            "stop": None,
            "target1": None,
            "target2": None,
            "notes": "",
        }
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["symbol"] = symbol.strip().upper()
            return data
        except Exception as e:
            logger.warning("[TARGETS] Failed to load %s: %s", path, e)
            return {
                "symbol": symbol.strip().upper(),
                "entry_low": None,
                "entry_high": None,
                "stop": None,
                "target1": None,
                "target2": None,
                "notes": "",
            }


def put_targets(symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Store targets for symbol. Validates and persists."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise ValueError("Symbol required")

    out = {
        "symbol": sym,
        "entry_low": _safe_float(data.get("entry_low")),
        "entry_high": _safe_float(data.get("entry_high")),
        "stop": _safe_float(data.get("stop")),
        "target1": _safe_float(data.get("target1")),
        "target2": _safe_float(data.get("target2")),
        "notes": str(data.get("notes", ""))[:500],
    }

    path = _targets_path(sym)
    _ensure_targets_dir()
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
    return out


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
