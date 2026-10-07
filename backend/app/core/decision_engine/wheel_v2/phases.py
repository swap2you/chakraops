# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 Wheel V2 lifecycle phases."""

from __future__ import annotations

from enum import Enum


class WheelPhase(str, Enum):
    """Canonical Wheel lifecycle advisory phases (R38)."""

    OWNABILITY = "OWNABILITY"
    CSP_ENTRY = "CSP_ENTRY"
    CSP_MANAGE = "CSP_MANAGE"
    ASSIGNMENT = "ASSIGNMENT"
    CC_ENTRY = "CC_ENTRY"
    CC_MANAGE = "CC_MANAGE"
    EXIT = "EXIT"
    SHARES_ENTRY = "SHARES_ENTRY"
    SHARES_MANAGE = "SHARES_MANAGE"
    STAY_IN_CASH = "STAY_IN_CASH"


PHASE_LABELS = {
    WheelPhase.OWNABILITY: "Ownability check",
    WheelPhase.CSP_ENTRY: "Cash-secured put entry",
    WheelPhase.CSP_MANAGE: "CSP management",
    WheelPhase.ASSIGNMENT: "Assignment advisory",
    WheelPhase.CC_ENTRY: "Covered call entry",
    WheelPhase.CC_MANAGE: "Covered call management",
    WheelPhase.EXIT: "Exit",
    WheelPhase.SHARES_ENTRY: "Shares entry",
    WheelPhase.SHARES_MANAGE: "Shares management",
    WheelPhase.STAY_IN_CASH: "Stay in cash",
}


def phase_label(phase: WheelPhase | str) -> str:
    """Safe UI label for a phase (never raw FAIL_/WARN_)."""
    try:
        p = phase if isinstance(phase, WheelPhase) else WheelPhase(str(phase))
    except ValueError:
        return "Wheel advisory"
    return PHASE_LABELS.get(p, "Wheel advisory")
