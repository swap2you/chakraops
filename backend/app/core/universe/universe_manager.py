# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 8.7: Universe Manager — curated manifest + tiered cadence + round-robin.

Universe is curated (operator-editable), not screened.
Tiering controls evaluation cadence.
Round-robin prevents stalls when max_symbols_per_cycle caps selection.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.core.universe.universe_state_store import UniverseStateStore

logger = logging.getLogger(__name__)

_DEFAULT_MANIFEST: Dict[str, Any] = {
    "version": 1,
    "default_enabled": True,
    "max_symbols_per_cycle": 25,
    "cycle_minutes": 30,
    "tiers": [
        {
            "name": "CORE",
            "enabled": True,
            "cadence_minutes": 30,
            "max_new_positions": 3,
            "symbols": ["SPY", "QQQ", "AAPL", "MSFT"],
        },
    ],
    "symbol_overrides": {},
}


def _default_manifest_path() -> Path:
    repo = Path(__file__).resolve().parents[3]
    return repo / "artifacts" / "config" / "universe.json"


def load_universe_manifest(path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Load universe manifest from JSON.
    If file missing, return safe default manifest with CORE tier only.
    If invalid (missing required keys), raise ValueError.
    """
    p = Path(path) if path is not None else _default_manifest_path()
    if not p.exists():
        logger.info("[UNIVERSE] Manifest not found at %s, using default", p)
        return dict(_DEFAULT_MANIFEST)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"Universe manifest invalid or unreadable: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("Universe manifest must be a JSON object")
    # Validate required keys
    if "tiers" not in data or not isinstance(data["tiers"], list):
        raise ValueError("Universe manifest must have 'tiers' as a non-empty list")
    for i, t in enumerate(data["tiers"]):
        if not isinstance(t, dict):
            raise ValueError(f"tier[{i}] must be an object")
        if "name" not in t or "symbols" not in t:
            raise ValueError(f"tier[{i}] must have 'name' and 'symbols'")
        if not isinstance(t.get("symbols"), list):
            raise ValueError(f"tier[{i}].symbols must be a list")
    if "max_symbols_per_cycle" not in data:
        data["max_symbols_per_cycle"] = 25
    if "symbol_overrides" not in data:
        data["symbol_overrides"] = {}
    return data


def get_symbols_for_cycle(
    manifest: Dict[str, Any],
    now_utc: datetime,
    state_store: UniverseStateStore,
) -> List[str]:
    """
    Return symbols to evaluate for this cycle using tiered cadence + round-robin.

    - A tier is "due" if (now - last_run) >= cadence_minutes.
    - Apply symbol_overrides: enabled=false -> skip.
    - Combine symbols from due tiers; enforce max_symbols_per_cycle via round-robin.
    - Update state (tier_last_run_utc, tier_cursor) for next run.
    - If no tiers due, return [].
    """
    state = state_store.load()
    tier_last = state.get("tier_last_run_utc") or {}
    tier_cursor = state.get("tier_cursor") or {}
    overrides = manifest.get("symbol_overrides") or {}
    max_per_cycle = int(manifest.get("max_symbols_per_cycle") or 25)

    due_tiers: List[Dict[str, Any]] = []
    for t in manifest.get("tiers") or []:
        if not t.get("enabled", True):
            continue
        name = t.get("name") or "?"
        cadence = int(t.get("cadence_minutes") or 30)
        last_iso = tier_last.get(name)
        if last_iso:
            try:
                last_dt = datetime.fromisoformat(last_iso.replace("Z", "+00:00"))
                delta_min = (now_utc - last_dt).total_seconds() / 60.0
                if delta_min < cadence:
                    continue
            except (ValueError, TypeError):
                pass
        due_tiers.append(t)

    if not due_tiers:
        logger.info("[UNIVERSE] No tiers due this cycle; returning empty list")
        return []

    # Build candidates from due tiers, applying overrides
    candidates_by_tier: List[tuple[str, List[str]]] = []
    for t in due_tiers:
        name = t.get("name") or "?"
        raw = list(t.get("symbols") or [])
        filtered: List[str] = []
        for sym in raw:
            s = (sym or "").strip().upper()
            if not s:
                continue
            ov = overrides.get(s) if isinstance(overrides.get(s), dict) else None
            if ov is not None and ov.get("enabled") is False:
                continue
            filtered.append(s)
        if filtered:
            candidates_by_tier.append((name, filtered))

    # Round-robin: use cursor per tier to pick symbols up to max_per_cycle
    selected: List[str] = []
    seen: set = set()
    budget = max_per_cycle
    cursors = dict(tier_cursor)

    while budget > 0 and candidates_by_tier:
        made_progress = False
        for tier_name, syms in candidates_by_tier:
            if budget <= 0:
                break
            if not syms:
                continue
            cur = cursors.get(tier_name, 0) % len(syms)
            sym = syms[cur]
            if sym not in seen:
                selected.append(sym)
                seen.add(sym)
                budget -= 1
                made_progress = True
            cursors[tier_name] = cur + 1
        if not made_progress:
            break

    # Update state: mark tiers as run, persist cursors
    now_iso = now_utc.isoformat()
    for tier_name, _ in candidates_by_tier:
        tier_last[tier_name] = now_iso
    state["tier_last_run_utc"] = tier_last
    state["tier_cursor"] = cursors
    state_store.save(state)

    return selected
