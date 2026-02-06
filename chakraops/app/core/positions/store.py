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


def list_positions(status: Optional[str] = None) -> List[Position]:
    """List all positions, optionally filtered by status."""
    positions = _load_all()
    if status:
        positions = [p for p in positions if p.status == status]
    # Sort by opened_at descending (newest first)
    positions.sort(key=lambda p: p.opened_at, reverse=True)
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

    for key in ("status", "closed_at", "notes"):
        if key in updates:
            setattr(target, key, updates[key])

    _save_all(positions)
    logger.info("[POSITIONS] Updated position %s", position_id)
    return target
