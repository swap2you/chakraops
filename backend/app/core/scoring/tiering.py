# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.2: Tier assignment (informational only). Does not change mode_decision or Stage-2."""

from __future__ import annotations

from app.core.scoring.config import TIER_A_MIN, TIER_B_MIN, TIER_C_MIN


def assign_tier(mode_decision: str, composite_score: float) -> str:
    """
    Assign tier from mode and composite score.
    Returns "A" | "B" | "C" | "NONE". Configurable via scoring config.
    """
    mode = (mode_decision or "NONE").strip().upper()
    if mode == "NONE":
        return "NONE"
    try:
        s = float(composite_score)
    except (TypeError, ValueError):
        return "NONE"
    if s >= TIER_A_MIN:
        return "A"
    if s >= TIER_B_MIN:
        return "B"
    if s >= TIER_C_MIN:
        return "C"
    return "NONE"
