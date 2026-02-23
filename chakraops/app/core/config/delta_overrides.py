# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.2: Per-symbol delta band overrides (advanced). Stored in chakraops/data/delta_overrides.json; NOT in out/."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# chakraops/app/core/config -> chakraops = parents[3]
_CHAKRAOPS_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PATH = _CHAKRAOPS_ROOT / "data" / "delta_overrides.json"

_path_override: Optional[Path] = None
_lock = threading.RLock()


def get_delta_overrides_path() -> Path:
    if _path_override is not None:
        return _path_override
    return _DEFAULT_PATH


def set_delta_overrides_path(path: Path) -> None:
    global _path_override
    with _lock:
        _path_override = Path(path).resolve()


def reset_delta_overrides_path() -> None:
    global _path_override
    with _lock:
        _path_override = None


def load_delta_overrides() -> Dict[str, Dict[str, Any]]:
    """Load { symbol: { delta_lo, delta_hi, updated_at_utc } }. Returns {} on missing/invalid."""
    path = get_delta_overrides_path()
    with _lock:
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            out = {}
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(k, str):
                    lo = v.get("delta_lo")
                    hi = v.get("delta_hi")
                    if lo is not None and hi is not None:
                        try:
                            out[k.strip().upper()] = {
                                "delta_lo": float(lo),
                                "delta_hi": float(hi),
                                "updated_at_utc": v.get("updated_at_utc") or "",
                            }
                        except (TypeError, ValueError):
                            pass
            return out
        except Exception:
            return {}


def get_effective_delta_band(
    symbol: str,
    canonical_lo: float,
    canonical_hi: float,
    max_widen: float,
) -> Tuple[float, float]:
    """Return (delta_lo, delta_hi) for symbol: override if present and within max_widen, else canonical."""
    overrides = load_delta_overrides()
    sym = (symbol or "").strip().upper()
    if not sym or sym not in overrides:
        return canonical_lo, canonical_hi
    o = overrides[sym]
    lo, hi = o["delta_lo"], o["delta_hi"]
    if lo > hi:
        return canonical_lo, canonical_hi
    # Enforce max_widen: override band must be within [canonical_lo - max_widen, canonical_hi + max_widen]
    min_lo = canonical_lo - max_widen
    max_hi = canonical_hi + max_widen
    lo = max(lo, min_lo)
    hi = min(hi, max_hi)
    if lo > hi:
        return canonical_lo, canonical_hi
    return lo, hi


def save_delta_override(
    symbol: str,
    delta_lo: float,
    delta_hi: float,
    max_widen: float,
    canonical_lo: float,
    canonical_hi: float,
) -> Tuple[bool, Optional[str]]:
    """Save override for symbol. Enforce max_widen. Returns (success, error_message)."""
    from datetime import datetime, timezone

    sym = (symbol or "").strip().upper()
    if not sym:
        return False, "Symbol required"
    if delta_lo > delta_hi:
        return False, "delta_lo must be <= delta_hi"
    min_lo = canonical_lo - max_widen
    max_hi = canonical_hi + max_widen
    if delta_lo < min_lo or delta_hi > max_hi:
        return False, f"Override must be within [{min_lo:.2f}, {max_hi:.2f}] (max_widen={max_widen})"
    overrides = load_delta_overrides()
    overrides[sym] = {
        "delta_lo": delta_lo,
        "delta_hi": delta_hi,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = get_delta_overrides_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        try:
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(overrides, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(path)
            return True, None
        except Exception as e:
            return False, str(e)


def delete_delta_override(symbol: str) -> bool:
    """Remove override for symbol. Returns True if removed or was absent."""
    sym = (symbol or "").strip().upper()
    if not sym:
        return False
    overrides = load_delta_overrides()
    if sym not in overrides:
        return True
    del overrides[sym]
    path = get_delta_overrides_path()
    with _lock:
        try:
            if not overrides:
                if path.exists():
                    path.unlink()
                return True
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(overrides, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            tmp.replace(path)
            return True
        except Exception:
            return False
