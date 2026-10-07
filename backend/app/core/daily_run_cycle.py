# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Daily run cycle model for deterministic execution (Phase 6.2).

One cycle per market date (cycle_id = YYYY-MM-DD). Phases advance in order:
SNAPSHOT -> DECISION -> TRADE_PROPOSAL -> OBSERVABILITY -> COMPLETE.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DailyRunPhase(str, Enum):
    """Phase of the daily pipeline. Order: SNAPSHOT -> DECISION -> TRADE_PROPOSAL -> OBSERVABILITY -> COMPLETE."""

    SNAPSHOT = "SNAPSHOT"
    DECISION = "DECISION"
    TRADE_PROPOSAL = "TRADE_PROPOSAL"
    OBSERVABILITY = "OBSERVABILITY"
    COMPLETE = "COMPLETE"


# Ordered list for validation
PHASE_ORDER = [
    DailyRunPhase.SNAPSHOT,
    DailyRunPhase.DECISION,
    DailyRunPhase.TRADE_PROPOSAL,
    DailyRunPhase.OBSERVABILITY,
    DailyRunPhase.COMPLETE,
]


@dataclass
class DailyRunCycle:
    """One row per cycle_id (YYYY-MM-DD). Enforces exactly one deterministic daily cycle per date."""

    cycle_id: str  # YYYY-MM-DD, local market date
    started_at: str  # ISO datetime
    completed_at: Optional[str]  # ISO datetime, set when phase = COMPLETE
    phase: DailyRunPhase


def phase_order_index(phase: DailyRunPhase) -> int:
    """Return index in phase order (0 = SNAPSHOT, 4 = COMPLETE)."""
    try:
        return PHASE_ORDER.index(phase)
    except ValueError:
        return -1


__all__ = ["DailyRunCycle", "DailyRunPhase", "PHASE_ORDER", "phase_order_index"]
