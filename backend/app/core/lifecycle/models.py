# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2C: Lifecycle models — events, actions, states, exit reasons."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class LifecycleState(str, Enum):
    """Position lifecycle states. Derived from tracked positions and evaluation."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"
    ABORTED = "ABORTED"


class LifecycleAction(str, Enum):
    """Directive actions — what the user should do now."""

    ENTER = "ENTER"
    HOLD = "HOLD"
    SCALE_OUT = "SCALE_OUT"
    EXIT = "EXIT"
    ABORT = "ABORT"


class ExitReason(str, Enum):
    """Reason for exit directive."""

    TARGET_1 = "TARGET_1"
    TARGET_2 = "TARGET_2"
    STOP_LOSS = "STOP_LOSS"
    REGIME_BREAK = "REGIME_BREAK"
    DATA_FAILURE = "DATA_FAILURE"


@dataclass
class LifecycleEvent:
    """A lifecycle event that may trigger an alert."""

    position_id: str
    symbol: str
    lifecycle_state: LifecycleState
    action: LifecycleAction
    reason: Optional[ExitReason] = None
    directive: str = ""
    triggered_at: str = ""
    eval_run_id: str = ""
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.triggered_at:
            self.triggered_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position_id": self.position_id,
            "symbol": self.symbol,
            "lifecycle_state": self.lifecycle_state.value,
            "action": self.action.value,
            "reason": self.reason.value if self.reason else None,
            "directive": self.directive,
            "triggered_at": self.triggered_at,
            "eval_run_id": self.eval_run_id,
            "meta": self.meta,
        }
