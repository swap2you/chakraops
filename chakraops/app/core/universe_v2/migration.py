# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Universe V2 (R36.2) migration — conservative, idempotent state initialization.

Initializes durable lifecycle state from the effective research pool without
auto-admitting, preserving overlay removals/additions. Idempotent (re-running is a no-op
when state already exists at the current schema). Backs up existing state before writing
and supports rollback. Writes only under ``<out>/universe_v2/`` — never a tracked file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from app.core.universe_v2 import store
from app.core.universe_v2.model import (
    LIFECYCLE_REMOVED,
    LIFECYCLE_WATCH,
    SCHEMA_VERSION,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _effective_and_removed() -> Tuple[List[str], List[str]]:
    from app.api import data_health

    effective = [str(s).strip().upper() for s in data_health.get_universe_symbols()]
    removed: List[str] = []
    try:
        from app.core.universe.universe_overrides import snapshot_overlay

        ov = snapshot_overlay()
        removed = [str(s).strip().upper() for s in (ov.get("removed") or [])]
    except Exception as e:
        logger.warning("[UNIVERSE_V2] migration overlay read failed: %s", e)
    return effective, removed


def _conservative_symbol(in_pool: bool, removed: bool) -> Dict[str, Any]:
    return {
        "lifecycle_state": LIFECYCLE_REMOVED if removed else LIFECYCLE_WATCH,
        "pass_streak": 0,
        "fail_streak": 0,
        "transitions": [],
        "override": {"kind": "EXCLUDE", "reason": "operator removal", "at_utc": None} if removed else None,
        "in_research_pool": in_pool,
    }


def initialize_universe_v2(force: bool = False) -> Dict[str, Any]:
    """Conservatively initialize (or extend) durable Universe V2 state.

    Idempotent: when state already exists at the current schema and no new pool symbols
    are present, this makes no write and returns the existing state unchanged.
    """
    effective, removed = _effective_and_removed()
    effective_set = set(effective)
    removed_set = set(removed)
    all_symbols = sorted(effective_set | removed_set)

    state = store.load_state()
    existing = dict(state.get("symbols") or {})
    is_current = state.get("schema_version") == SCHEMA_VERSION and bool(existing)

    if is_current and not force:
        missing = [s for s in all_symbols if s not in existing]
        if not missing:
            logger.info("[UNIVERSE_V2] migration no-op (state present, no new symbols)")
            return state
        # Additively add new pool symbols as conservative WATCH; never reset existing.
        store.backup_state()
        for s in missing:
            existing[s] = _conservative_symbol(s in effective_set, s in removed_set)
        state["symbols"] = existing
        store.save_state(state)
        logger.info("[UNIVERSE_V2] migration added %d new symbols", len(missing))
        return state

    # Fresh (or forced) conservative initialization.
    store.backup_state()
    symbols_state = {
        s: _conservative_symbol(s in effective_set, s in removed_set) for s in all_symbols
    }
    new_state = {
        "schema_version": SCHEMA_VERSION,
        "version": int(state.get("version") or 0),
        "updated_at_utc": _now_iso(),
        "symbols": symbols_state,
    }
    store.save_state(new_state)
    logger.info("[UNIVERSE_V2] migration initialized %d symbols (conservative WATCH)", len(symbols_state))
    return new_state


def rollback() -> bool:
    """Restore the durable state from the single-slot backup. Returns True if restored."""
    ok = store.restore_state()
    logger.info("[UNIVERSE_V2] rollback restored=%s", ok)
    return ok
