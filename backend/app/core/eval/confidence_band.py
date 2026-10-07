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
    """Band and suggested capital % for display. Phase 3: band_reason explains why (so Band C is not unexplained)."""
    band: str  # "A" | "B" | "C"
    suggested_capital_pct: float
    band_reason: Optional[str] = None  # e.g. "Band C: data_completeness < 0.75"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "band": self.band,
            "suggested_capital_pct": self.suggested_capital_pct,
            "band_reason": self.band_reason,
        }


def _get_band_limits() -> tuple:
    """Band A/B minimum scores from config (avoid circular import)."""
    try:
        from app.core.eval.scoring import get_band_limits
        return get_band_limits()
    except Exception:
        return 78, 60


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
    Phase 3: Band A/B/C derived from score + gates; band_reason explains why (Band C never unexplained).

    Rules:
    - A: ELIGIBLE, score >= band_a_min (78), RISK_ON, data_completeness >= 0.75, liquidity_ok, no position_open, completeness >= 0.9.
    - B: ELIGIBLE with score >= band_b_min (60) but any gate not meeting A; or NEUTRAL/minor gaps/position open.
    - C: Not ELIGIBLE, or score < band_b_min, or data_completeness < 0.75; band_reason set.
    """
    verdict_upper = (verdict or "").strip().upper()
    regime_upper = (regime or "").strip().upper()
    band_a_min, band_b_min = _get_band_limits()

    def make_hint(band: ConfidenceBand, reason: str) -> CapitalHint:
        return CapitalHint(
            band=band.value,
            suggested_capital_pct=BAND_CAPITAL_PCT[band],
            band_reason=reason,
        )

    # C: Not ELIGIBLE
    if verdict_upper not in ("ELIGIBLE", "GREEN"):
        if verdict_upper == "HOLD":
            reason = f"Band C: verdict HOLD (score {score})"
        elif verdict_upper in ("BLOCKED", "UNKNOWN"):
            reason = f"Band C: verdict {verdict_upper}"
        else:
            reason = f"Band C: verdict {verdict_upper}"
        return make_hint(ConfidenceBand.C, reason)

    # ELIGIBLE path: gates for A/B/C
    if data_completeness < 0.75:
        return make_hint(ConfidenceBand.C, f"Band C: data_completeness {data_completeness:.2f} < 0.75")
    if score < band_b_min:
        return make_hint(ConfidenceBand.C, f"Band C: score {score} < {band_b_min}")

    # B: ELIGIBLE but not A
    if regime_upper != "RISK_ON":
        return make_hint(ConfidenceBand.B, f"Band B: regime {regime_upper or 'unknown'} (not RISK_ON)")
    if not liquidity_ok:
        return make_hint(ConfidenceBand.B, "Band B: liquidity not OK")
    if position_open:
        return make_hint(ConfidenceBand.B, "Band B: position already open")
    if data_completeness < 0.9:
        return make_hint(ConfidenceBand.B, f"Band B: data_completeness {data_completeness:.2f} < 0.9")
    if score < band_a_min:
        return make_hint(ConfidenceBand.B, f"Band B: score {score} < {band_a_min}")

    return make_hint(ConfidenceBand.A, f"Band A: score {score} >= {band_a_min}, RISK_ON, data complete, liquidity OK")
