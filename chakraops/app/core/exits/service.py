# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Exit service — validate and persist manual exits."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.core.exits.models import ExitRecord, VALID_EXIT_REASONS, VALID_EXIT_INITIATORS, VALID_EXIT_EVENT_TYPES
from app.core.exits import store as exit_store
from app.core.positions import store as position_store

logger = logging.getLogger(__name__)


def validate_log_exit(data: Dict[str, Any], position_id: str) -> List[str]:
    """Validate exit log payload. Returns list of error messages."""
    errors: List[str] = []
    if not position_id or not isinstance(position_id, str):
        errors.append("position_id is required")
    else:
        pos = position_store.get_position(position_id)
        if pos is None:
            errors.append(f"Position {position_id} not found")
    if not data.get("exit_date"):
        errors.append("exit_date is required (YYYY-MM-DD)")
    exit_reason = (data.get("exit_reason") or "").strip()
    if exit_reason not in VALID_EXIT_REASONS:
        errors.append(
            f"exit_reason must be one of {sorted(VALID_EXIT_REASONS)}, got: {repr(exit_reason)}"
        )
    exit_initiator = (data.get("exit_initiator") or "").strip()
    if exit_initiator not in VALID_EXIT_INITIATORS:
        errors.append(
            f"exit_initiator must be one of {sorted(VALID_EXIT_INITIATORS)}, got: {repr(exit_initiator)}"
        )
    try:
        conf = int(data.get("confidence_at_exit", 3))
        if conf < 1 or conf > 5:
            errors.append("confidence_at_exit must be 1-5")
    except (TypeError, ValueError):
        errors.append("confidence_at_exit must be an integer 1-5")
    event_type = (data.get("event_type") or "FINAL_EXIT").strip()
    if event_type not in VALID_EXIT_EVENT_TYPES:
        errors.append(f"event_type must be one of {sorted(VALID_EXIT_EVENT_TYPES)}, got: {repr(event_type)}")
    return errors


def log_exit(position_id: str, data: Dict[str, Any]) -> Tuple[Optional[ExitRecord], List[str]]:
    """Log a manual exit for a position. Updates position to CLOSED.

    Returns (exit_record, errors). On success, errors is empty.
    """
    errors = validate_log_exit(data, position_id)
    if errors:
        return None, errors

    pos = position_store.get_position(position_id)
    if pos is None:
        return None, [f"Position {position_id} not found"]

    event_type = (data.get("event_type") or "FINAL_EXIT").strip()
    if event_type not in VALID_EXIT_EVENT_TYPES:
        event_type = "FINAL_EXIT"

    try:
        record = ExitRecord(
            position_id=position_id,
            exit_date=str(data.get("exit_date", "")).strip()[:10],
            exit_price=float(data.get("exit_price", 0)),
            realized_pnl=float(data.get("realized_pnl", 0)),
            fees=float(data.get("fees", 0)),
            exit_reason=(data.get("exit_reason") or "").strip(),
            exit_initiator=(data.get("exit_initiator") or "MANUAL").strip(),
            confidence_at_exit=int(data.get("confidence_at_exit", 3)),
            notes=str(data.get("notes", ""))[:1000],
            event_type=event_type,
        )
    except ValueError as e:
        return None, [str(e)]

    exit_store.save_exit(record)
    # Phase 5: SCALE_OUT -> PARTIAL_EXIT; FINAL_EXIT -> CLOSED
    if event_type == "FINAL_EXIT":
        position_store.update_position(position_id, {
            "status": "CLOSED",
            "closed_at": record.exit_date,
        })
    else:
        position_store.update_position(position_id, {"status": "PARTIAL_EXIT"})
    logger.info("[EXITS] Logged exit for %s: %s", position_id, record.exit_reason)
    return record, []
