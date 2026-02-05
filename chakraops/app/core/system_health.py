# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""System Health & Readiness Snapshot.

This module provides a pure, deterministic function for computing system health
and readiness based on market conditions, candidate counts, and error/warning metrics.

The health computation is stateless, does not access databases, and never mutates
system state. It produces a SystemHealthSnapshot summarizing system safety and stability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SystemHealthSnapshot:
    """System health and readiness snapshot.
    
    Attributes
    ----------
    regime:
        Market regime: "RISK_ON" | "RISK_OFF".
    regime_confidence:
        Regime confidence percentage (0-100).
    total_candidates:
        Total number of CSP candidates found.
    actionable_candidates:
        Number of actionable candidates (approved for execution).
    blocked_actions:
        Number of blocked actions.
    error_count_24h:
        Number of errors in last 24 hours.
    warning_count_24h:
        Number of warnings in last 24 hours.
    health_score:
        Health score (0-100). Higher is better.
    status:
        Health status: "HEALTHY" | "DEGRADED" | "HALT".
    computed_at:
        Timestamp when this snapshot was computed (ISO format).
    regime_reason:
        Optional reason when regime is RISK_OFF (e.g. "volatility_spike", Phase 2.2).
    """
    regime: str  # RISK_ON | RISK_OFF
    regime_confidence: int  # 0-100
    total_candidates: int
    actionable_candidates: int
    blocked_actions: int
    error_count_24h: int
    warning_count_24h: int
    health_score: int  # 0-100
    status: str  # HEALTHY | DEGRADED | HALT
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    regime_reason: Optional[str] = None  # e.g. "volatility_spike" when kill switch triggers


def compute_system_health(
    regime: str,
    regime_confidence: int,
    total_candidates: int = 0,
    actionable_candidates: int = 0,
    blocked_actions: int = 0,
    error_count_24h: int = 0,
    warning_count_24h: int = 0,
    regime_reason: Optional[str] = None,
) -> SystemHealthSnapshot:
    """Compute system health and readiness snapshot.
    
    This function is deterministic, stateless, and never mutates system state
    or accesses databases. It computes a health score based on various factors
    and returns a SystemHealthSnapshot.
    
    Parameters
    ----------
    regime:
        Market regime: "RISK_ON" | "RISK_OFF".
    regime_confidence:
        Regime confidence percentage (0-100).
    total_candidates:
        Total number of CSP candidates found (default: 0).
    actionable_candidates:
        Number of actionable candidates approved for execution (default: 0).
    blocked_actions:
        Number of blocked actions (default: 0).
    error_count_24h:
        Number of errors in last 24 hours (default: 0).
    warning_count_24h:
        Number of warnings in last 24 hours (default: 0).
    
    Returns
    -------
    SystemHealthSnapshot
        System health snapshot with score, status, and all metrics.
    
    Health Scoring Rules (starting at 100):
    ---------------------------------------
    1. -20 if regime_confidence < 70
    2. -10 per ERROR in last 24h (cap at -40)
    3. -10 if blocked_actions > actionable_candidates
    4. -30 if regime == RISK_OFF
    5. Clamp score to 0-100
    
    Status Mapping:
    ---------------
    - score >= 80: HEALTHY
    - score 50-79: DEGRADED
    - score < 50: HALT
    """
    # Normalize regime
    regime_upper = regime.upper() if regime else "RISK_OFF"
    
    # Ensure regime_confidence is in valid range
    regime_confidence = max(0, min(100, regime_confidence))
    
    # Initialize score at 100
    score = 100
    
    # Rule 1: -20 if regime_confidence < 70
    if regime_confidence < 70:
        score -= 20
    
    # Rule 2: -10 per ERROR in last 24h (cap at -40)
    error_penalty = min(40, error_count_24h * 10)
    score -= error_penalty
    
    # Rule 3: -10 if blocked_actions > actionable_candidates
    if blocked_actions > actionable_candidates:
        score -= 10
    
    # Rule 4: -30 if regime == RISK_OFF
    if regime_upper == "RISK_OFF":
        score -= 30
    
    # Rule 5: Clamp score to 0-100
    score = max(0, min(100, score))
    
    # Status mapping
    if score >= 80:
        status = "HEALTHY"
    elif score >= 50:
        status = "DEGRADED"
    else:
        status = "HALT"
    
    # Build snapshot
    snapshot = SystemHealthSnapshot(
        regime=regime_upper,
        regime_confidence=regime_confidence,
        total_candidates=total_candidates,
        actionable_candidates=actionable_candidates,
        blocked_actions=blocked_actions,
        error_count_24h=error_count_24h,
        warning_count_24h=warning_count_24h,
        health_score=score,
        status=status,
        computed_at=datetime.now(timezone.utc).isoformat(),
        regime_reason=regime_reason,
    )
    
    # Log single summary line
    logger.info(
        f"SystemHealth: score={score} | status={status} | regime={regime_upper} | "
        f"confidence={regime_confidence}% | candidates={total_candidates} | "
        f"actionable={actionable_candidates} | blocked={blocked_actions} | "
        f"errors_24h={error_count_24h} | warnings_24h={warning_count_24h}"
    )
    
    return snapshot


__all__ = ["SystemHealthSnapshot", "compute_system_health"]
