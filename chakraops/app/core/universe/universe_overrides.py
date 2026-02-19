# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 21.3: Universe overlay — add/remove symbols without mutating CSV.

Overlay file: out/universe_overrides.json
Structure: { "added": ["SYM"], "removed": ["SYM"], "updated_at": "ISO8601" }
Effective universe = (base_symbols ∪ added) − removed, stable sort.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = __import__("logging").getLogger(__name__)

_LOCK = threading.Lock()

# Validation: 1-10 chars, uppercase letters, digits, dot, hyphen only
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _overlay_path() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except Exception:
        base = Path("out")
    base.mkdir(parents=True, exist_ok=True)
    return base / "universe_overrides.json"


def _load_overlay() -> Dict[str, Any]:
    """Load overlay from file. Returns { added: [], removed: [], updated_at: "" }. Caller holds _LOCK if needed."""
    path = _overlay_path()
    if not path.exists():
        return {"added": [], "removed": [], "updated_at": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("[UNIVERSE_OVERLAY] Failed to load %s: %s", path, e)
        return {"added": [], "removed": [], "updated_at": ""}
    added = list(data.get("added") or [])
    removed = list(data.get("removed") or [])
    return {
        "added": [str(s).strip().upper() for s in added if str(s).strip()],
        "removed": [str(s).strip().upper() for s in removed if str(s).strip()],
        "updated_at": str(data.get("updated_at") or ""),
    }


def _save_overlay(overlay: Dict[str, Any]) -> None:
    """Write overlay to file. Caller holds _LOCK if needed."""
    path = _overlay_path()
    now = datetime.now(timezone.utc).isoformat()
    overlay = {**overlay, "updated_at": now}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(overlay, f, indent=2)


def validate_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Validate symbol: 1-10 chars, [A-Z0-9.-] only.
    Returns (ok, error_message).
    """
    s = (symbol or "").strip().upper()
    if not s:
        return False, "Symbol is required"
    if len(s) > 10:
        return False, "Symbol must be at most 10 characters"
    if not _SYMBOL_PATTERN.match(s):
        return False, "Symbol must contain only letters, numbers, dot, or hyphen (1-10 chars)"
    return True, ""


def get_effective_symbols(base: List[str]) -> List[str]:
    """
    Return (base ∪ added) − removed, stable sorted.
    base order is preserved for base symbols; then added (sorted); removed are excluded.
    """
    overlay = _load_overlay()
    base_set = {str(s).strip().upper() for s in base if str(s).strip()}
    added = overlay.get("added") or []
    removed_set = set(overlay.get("removed") or [])
    out: List[str] = []
    seen = set()
    for s in base:
        sym = str(s).strip().upper()
        if not sym or sym in seen:
            continue
        if sym in removed_set:
            continue
        seen.add(sym)
        out.append(sym)
    for sym in sorted(added):
        if sym in seen or sym in removed_set:
            continue
        seen.add(sym)
        out.append(sym)
    return sorted(out)


def add_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Add symbol to overlay (to added, and remove from removed if present).
    Returns (success, error_message). Idempotent if already in effective list.
    """
    ok, err = validate_symbol(symbol)
    if not ok:
        return False, err
    sym = symbol.strip().upper()
    with _LOCK:
        overlay = _load_overlay()
        added = list(overlay.get("added") or [])
        removed = list(overlay.get("removed") or [])
        if sym in removed:
            removed = [s for s in removed if s != sym]
        if sym not in added:
            added = list(added) + [sym]
        overlay["added"] = added
        overlay["removed"] = removed
        _save_overlay(overlay)
    return True, ""


def remove_symbol(symbol: str) -> Tuple[bool, str]:
    """
    Remove symbol (add to removed, remove from added if present).
    Returns (success, error_message). Idempotent.
    """
    s = (symbol or "").strip().upper()
    if not s:
        return False, "Symbol is required"
    with _LOCK:
        overlay = _load_overlay()
        added = [x for x in (overlay.get("added") or []) if x != s]
        removed = list(overlay.get("removed") or [])
        if s not in removed:
            removed = removed + [s]
        overlay["added"] = added
        overlay["removed"] = removed
        _save_overlay(overlay)
    return True, ""


def reset_overlay() -> None:
    """Clear overlay (added and removed)."""
    with _LOCK:
        _save_overlay({"added": [], "removed": [], "updated_at": ""})


def get_overlay_counts() -> Tuple[int, int]:
    """Return (len(added), len(removed))."""
    overlay = _load_overlay()
    return len(overlay.get("added") or []), len(overlay.get("removed") or [])
