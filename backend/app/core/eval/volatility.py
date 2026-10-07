# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Volatility logic: IV Rank bands only (Phase 3.2.3).

No trend logic. Bands and scoring are documented in docs/VOLATILITY_LOGIC.md.
"""

from __future__ import annotations

from typing import Optional

from app.core.config.wheel_strategy_config import (
    IVR_BANDS,
    IVR_HIGH,
    IVR_LOW,
    IVR_MID,
    get_ivr_bands,
)


def get_ivr_band(iv_rank: Optional[float]) -> Optional[str]:
    """
    Classify IV Rank into LOW, MID, or HIGH using wheel config IVR_BANDS only.
    No trend logic. Bands: LOW (0, 25), MID [25, 75), HIGH [75, 100].
    """
    if iv_rank is None:
        return None
    bands = get_ivr_bands()
    low_lo, low_hi = bands.get(IVR_LOW, (0, 25))
    mid_lo, mid_hi = bands.get(IVR_MID, (25, 75))
    if low_lo <= iv_rank < low_hi:
        return IVR_LOW
    if mid_lo <= iv_rank < mid_hi:
        return IVR_MID
    return IVR_HIGH


__all__ = ["get_ivr_band"]
