# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Phase 10: Confidence Scoring & Capital Bands.

GREEN (ELIGIBLE) does not imply equal conviction. Band A/B/C with suggested capital %.
- A: RISK_ON, no DATA_INCOMPLETE, liquidity strong
- B: NEUTRAL regime OR minor data gaps
- C: Any HOLD that barely passed, or lower conviction
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ConfidenceBand(str, Enum):
    """Confidence band for conviction level."""
    A = "A"  # Highest conviction
    B = "B"  # Moderate
    C = "C"  # Lower conviction / HOLD that barely passed


# Capital hints by band (suggested % of portfolio per position)
BAND_CAPITAL_PCT = {
    ConfidenceBand.A: 0.05,
    ConfidenceBand.B: 0.03,
    ConfidenceBand.C: 0.02,
}


@dataclass
class CapitalHint:
    """Band and suggested capital % for display."""
    band: str  # "A" | "B" | "C"
    suggested_capital_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "band": self.band,
            "suggested_capital_pct": self.suggested_capital_pct,
        }


def compute_confidence_band(
    verdict: str,
    regime: Optional[str],
    data_completeness: float,
    liquidity_ok: bool,
    score: int,
    position_open: bool = False,
) -> CapitalHint:
    """
    Compute confidence band and suggested capital % from evaluation result.

    Rules:
    - A: RISK_ON, no DATA_INCOMPLETE (completeness >= 0.75), liquidity strong, ELIGIBLE, not position_open.
    - B: NEUTRAL regime OR minor data gaps OR ELIGIBLE with position open elsewhere; or ELIGIBLE with completeness < 0.9.
    - C: HOLD that barely passed (score 50-65), or any BLOCKED/UNKNOWN; or data_completeness < 0.75.
    """
    verdict_upper = (verdict or "").strip().upper()
    regime_upper = (regime or "").strip().upper()

    # C: Low conviction
    if verdict_upper not in ("ELIGIBLE", "GREEN"):
        # HOLD that barely passed (score in capped range) or BLOCKED/UNKNOWN
        if verdict_upper == "HOLD" and 50 <= score <= 65:
            band = ConfidenceBand.C
        elif verdict_upper in ("BLOCKED", "UNKNOWN"):
            band = ConfidenceBand.C
        else:
            band = ConfidenceBand.C
        return CapitalHint(band=band.value, suggested_capital_pct=BAND_CAPITAL_PCT[band])

    # ELIGIBLE path
    if data_completeness < 0.75:
        return CapitalHint(band=ConfidenceBand.C.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.C])
    if regime_upper != "RISK_ON":
        return CapitalHint(band=ConfidenceBand.B.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.B])
    if not liquidity_ok:
        return CapitalHint(band=ConfidenceBand.B.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.B])
    if position_open:
        return CapitalHint(band=ConfidenceBand.B.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.B])
    if data_completeness < 0.9:
        return CapitalHint(band=ConfidenceBand.B.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.B])

    return CapitalHint(band=ConfidenceBand.A.value, suggested_capital_pct=BAND_CAPITAL_PCT[ConfidenceBand.A])
