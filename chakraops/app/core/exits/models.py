# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Exit record model — strict schema, no free-text reasons.
Phase 5: Multiple exit events per position (SCALE_OUT, FINAL_EXIT).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

# LOCKED ENUM — no free-text, no silent defaults
VALID_EXIT_REASONS = frozenset({
    "TARGET1",
    "TARGET2",
    "STOP_LOSS",
    "ABORT_REGIME",
    "ABORT_DATA",
    "MANUAL_EARLY",
    "EXPIRY",
    "ROLL",
})

VALID_EXIT_INITIATORS = frozenset({"LIFECYCLE_ENGINE", "MANUAL"})

# Phase 5: Event type for multi-exit lifecycle
VALID_EXIT_EVENT_TYPES = frozenset({"SCALE_OUT", "FINAL_EXIT"})


@dataclass
class ExitRecord:
    """Phase 4: Manual exit record. Phase 5: Supports event_type (SCALE_OUT | FINAL_EXIT)."""

    position_id: str
    exit_date: str  # YYYY-MM-DD
    exit_price: float
    realized_pnl: float
    fees: float
    exit_reason: str  # Must be in VALID_EXIT_REASONS
    exit_initiator: str  # LIFECYCLE_ENGINE | MANUAL
    confidence_at_exit: int  # 1-5
    notes: str = ""
    # Phase 5: SCALE_OUT = partial exit; FINAL_EXIT = position closed
    event_type: str = "FINAL_EXIT"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "position_id": self.position_id,
            "exit_date": self.exit_date,
            "exit_price": self.exit_price,
            "realized_pnl": self.realized_pnl,
            "fees": self.fees,
            "exit_reason": self.exit_reason,
            "exit_initiator": self.exit_initiator,
            "confidence_at_exit": self.confidence_at_exit,
            "notes": self.notes,
        }
        if self.event_type != "FINAL_EXIT":
            d["event_type"] = self.event_type
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExitRecord":
        if not isinstance(d, dict):
            raise ValueError("Exit record must be a dict")
        position_id = d.get("position_id")
        if not position_id or not isinstance(position_id, str):
            raise ValueError("position_id is required and must be a non-empty string")
        exit_date = d.get("exit_date")
        if not exit_date or not isinstance(exit_date, str):
            raise ValueError("exit_date is required and must be YYYY-MM-DD string")
        exit_reason = (d.get("exit_reason") or "").strip()
        if exit_reason not in VALID_EXIT_REASONS:
            raise ValueError(
                f"exit_reason must be one of {sorted(VALID_EXIT_REASONS)}, got: {repr(exit_reason)}"
            )
        exit_initiator = (d.get("exit_initiator") or "").strip()
        if exit_initiator not in VALID_EXIT_INITIATORS:
            raise ValueError(
                f"exit_initiator must be one of {sorted(VALID_EXIT_INITIATORS)}, got: {repr(exit_initiator)}"
            )
        try:
            exit_price = float(d.get("exit_price", 0))
            realized_pnl = float(d.get("realized_pnl", 0))
            fees = float(d.get("fees", 0))
            confidence_at_exit = int(d.get("confidence_at_exit", 3))
        except (TypeError, ValueError) as e:
            raise ValueError(f"exit_price, realized_pnl, fees, confidence_at_exit must be numeric: {e}")
        if confidence_at_exit < 1 or confidence_at_exit > 5:
            raise ValueError("confidence_at_exit must be 1-5")
        event_type = (d.get("event_type") or "FINAL_EXIT").strip()
        if event_type not in VALID_EXIT_EVENT_TYPES:
            event_type = "FINAL_EXIT"

        return cls(
            position_id=position_id,
            exit_date=exit_date,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            fees=fees,
            exit_reason=exit_reason,
            exit_initiator=exit_initiator,
            confidence_at_exit=confidence_at_exit,
            notes=str(d.get("notes", ""))[:1000],
            event_type=event_type,
        )
