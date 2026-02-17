# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 1: Position persistence — JSON file store under out/positions/positions.json."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import List, Optional

from app.core.positions.models import Position

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def _get_positions_dir() -> Path:
    try:
        from app.core.settings import get_output_dir
        base = Path(get_output_dir())
    except ImportError:
        base = Path("out")
    return base / "positions"


def _ensure_positions_dir() -> Path:
    p = _get_positions_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _positions_path() -> Path:
    return _ensure_positions_dir() / "positions.json"


_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_all() -> List[Position]:
    """Load all positions from JSON file."""
    path = _positions_path()
    if not path.exists():
        return []
    with _LOCK:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [Position.from_dict(d) for d in data]
            return []
        except Exception as e:
            logger.warning("[POSITIONS] Failed to load positions: %s", e)
            return []


def _save_all(positions: List[Position]) -> None:
    """Save all positions to JSON file."""
    path = _positions_path()
    _ensure_positions_dir()
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in positions], f, indent=2, default=str)
    logger.info("[POSITIONS] Saved %d positions", len(positions))


# ---------------------------------------------------------------------------
# CRUD operations
# ---------------------------------------------------------------------------


def list_positions(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    exclude_test: bool = False,
) -> List[Position]:
    """List all positions, optionally filtered by status, symbol, and exclude_test."""
    positions = _load_all()
    if status:
        positions = [p for p in positions if p.status == status]
    if symbol:
        sym_upper = (symbol or "").strip().upper()
        if sym_upper:
            positions = [p for p in positions if (p.symbol or "").strip().upper() == sym_upper]
    if exclude_test:
        positions = [p for p in positions if not getattr(p, "is_test", False)]
    # Sort by opened_at descending (newest first)
    positions.sort(key=lambda p: p.opened_at or "", reverse=True)
    return positions


def get_position(position_id: str) -> Optional[Position]:
    """Get a single position by ID."""
    positions = _load_all()
    for p in positions:
        if p.position_id == position_id:
            return p
    return None


def create_position(position: Position) -> Position:
    """Create a new position."""
    positions = _load_all()
    for p in positions:
        if p.position_id == position.position_id:
            raise ValueError(f"Position {position.position_id} already exists")
    positions.append(position)
    _save_all(positions)
    logger.info("[POSITIONS] Created position %s for %s", position.position_id, position.symbol)
    return position


def update_position(position_id: str, updates: dict) -> Optional[Position]:
    """Update an existing position."""
    positions = _load_all()
    target = None
    for p in positions:
        if p.position_id == position_id:
            target = p
            break
    if target is None:
        return None

    # Phase 1 keys + Phase 4/5 entry snapshot keys + Phase 10.0 close keys
    allowed_keys = frozenset({
        "status", "closed_at", "notes",
        "band", "risk_flags_at_entry", "portfolio_utilization_pct", "sector_exposure_pct",
        "thesis_strength", "data_sufficiency", "risk_amount_at_entry",
        "data_sufficiency_override", "data_sufficiency_override_source",
        "stop_price", "t1", "t2", "t3", "credit_expected",
        "close_debit", "close_price", "close_fees", "close_time_utc", "realized_pnl",
        "updated_at_utc",
    })
    for key, value in updates.items():
        if key in allowed_keys and hasattr(target, key):
            setattr(target, key, value)

    # Phase 5: Log data_sufficiency override distinctly
    if "data_sufficiency_override" in updates and updates.get("data_sufficiency_override"):
        try:
            from app.core.symbols.data_sufficiency import log_data_sufficiency_override
            log_data_sufficiency_override(
                position_id, getattr(target, "symbol", ""),
                updates["data_sufficiency_override"],
                updates.get("data_sufficiency_override_source") or "MANUAL",
            )
        except Exception as e:
            logger.warning("[POSITIONS] Failed to log data_sufficiency override: %s", e)

    _save_all(positions)
    logger.info("[POSITIONS] Updated position %s", position_id)
    return target


def delete_position(position_id: str) -> bool:
    """Delete a position. Returns True if deleted. Caller must enforce guardrails (is_test or CLOSED)."""
    positions = _load_all()
    before = len(positions)
    positions = [p for p in positions if p.position_id != position_id]
    if len(positions) == before:
        return False
    _save_all(positions)
    logger.info("[POSITIONS] Deleted position %s", position_id)
    return True
