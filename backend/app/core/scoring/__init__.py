# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.1/6.2: Scoring, tiering, ranking (diagnostic only). Never change mode_decision or Stage-2."""

from app.core.scoring.config import (
    ACCOUNT_EQUITY_DEFAULT,
    AFFORDABILITY_PCT_0,
    AFFORDABILITY_PCT_100,
    SCORE_WEIGHTS,
    SEVERITY_NOW_PCT,
    SEVERITY_READY_PCT,
    TIER_A_MIN,
    TIER_B_MIN,
    TIER_C_MIN,
)
from app.core.scoring.signal_score import compute_signal_score
from app.core.scoring.tiering import assign_tier
from app.core.scoring.ranking import rank_candidates
from app.core.scoring.severity import compute_alert_severity

__all__ = [
    "ACCOUNT_EQUITY_DEFAULT",
    "AFFORDABILITY_PCT_0",
    "AFFORDABILITY_PCT_100",
    "SCORE_WEIGHTS",
    "TIER_A_MIN",
    "TIER_B_MIN",
    "TIER_C_MIN",
    "SEVERITY_NOW_PCT",
    "SEVERITY_READY_PCT",
    "compute_signal_score",
    "assign_tier",
    "rank_candidates",
    "compute_alert_severity",
]
