# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.1: Manual position ledger. File-based JSON; no broker, no DB."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Default path relative to repo/cwd; callers can override via env or argument
DEFAULT_LEDGER_PATH = "artifacts/positions/open_positions.json"


def _default_path() -> Path:
    """Resolve default ledger path (repo root or cwd)."""
    return Path(DEFAULT_LEDGER_PATH).resolve()


def load_open_positions(ledger_path: Union[str, Path, None] = None) -> List[Dict[str, Any]]:
    """Load open positions from JSON. Returns list of position dicts; only status==OPEN."""
    path = Path(ledger_path) if ledger_path else _default_path()
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return [p for p in data if isinstance(p, dict) and (p.get("status") or "OPEN") == "OPEN"]


def save_open_positions(positions: List[Dict[str, Any]], ledger_path: Union[str, Path, None] = None) -> None:
    """Write full list of positions to JSON. Creates parent dirs if needed."""
    path = Path(ledger_path) if ledger_path else _default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2, default=str)


def _infer_option_type(mode: str) -> str:
    """CSP -> PUT, CC -> CALL. Default PUT."""
    m = (mode or "CSP").strip().upper()
    return "CALL" if m == "CC" else "PUT"


def add_position(
    symbol: str,
    mode: str,
    entry_date: str,
    expiration: str,
    strike: float,
    contracts: int,
    entry_premium: float,
    entry_spot: float,
    notes: str = "",
    option_type: Optional[str] = None,
    ledger_path: Union[str, Path, None] = None,
) -> Dict[str, Any]:
    """Append a new OPEN position and save. option_type: PUT/CALL; default from mode (CSP->PUT, CC->CALL)."""
    path = Path(ledger_path) if ledger_path else _default_path()
    # Load all (including closed) to preserve history when we write back
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            all_data = []
    else:
        all_data = []
    if not isinstance(all_data, list):
        all_data = []

    mode_upper = (mode or "CSP").strip().upper()
    ot = (option_type or "").strip().upper() if option_type else None
    if ot not in ("PUT", "CALL"):
        ot = _infer_option_type(mode_upper)

    position_id = str(uuid.uuid4())
    new_pos: Dict[str, Any] = {
        "position_id": position_id,
        "symbol": (symbol or "").strip().upper(),
        "mode": mode_upper,
        "option_type": ot,
        "entry_date": entry_date,
        "expiration": expiration,
        "strike": float(strike),
        "contracts": int(contracts),
        "entry_premium": float(entry_premium),
        "entry_spot": float(entry_spot),
        "notes": notes or "",
        "status": "OPEN",
    }
    all_data.append(new_pos)
    save_open_positions(all_data, path)
    return new_pos


def add_position_from_dict(
    position_dict: Dict[str, Any],
    ledger_path: Union[str, Path, None] = None,
) -> Dict[str, Any]:
    """Add a position from a dict (e.g. from JSON). Ensures position_id and status OPEN."""
    path = Path(ledger_path) if ledger_path else _default_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                all_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            all_data = []
    else:
        all_data = []
    if not isinstance(all_data, list):
        all_data = []
    p = dict(position_dict)
    if not p.get("position_id"):
        p["position_id"] = str(uuid.uuid4())
    p["status"] = "OPEN"
    # Backward compat: infer option_type from mode if missing
    if not (p.get("option_type") or "").strip().upper() in ("PUT", "CALL"):
        p["option_type"] = _infer_option_type(p.get("mode") or "CSP")
    all_data.append(p)
    save_open_positions(all_data, path)
    return p


def close_position(position_id: str, ledger_path: Union[str, Path, None] = None) -> bool:
    """Set position status to CLOSED. Returns True if found and updated."""
    path = Path(ledger_path) if ledger_path else _default_path()
    if not path.exists():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            all_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(all_data, list):
        return False
    found = False
    for p in all_data:
        if isinstance(p, dict) and p.get("position_id") == position_id:
            p["status"] = "CLOSED"
            found = True
            break
    if found:
        save_open_positions(all_data, path)
    return found
