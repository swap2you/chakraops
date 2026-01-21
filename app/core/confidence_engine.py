# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Confidence Aggregation & Noise Reduction Engine.

This module provides a deterministic function for computing confidence scores
for ActionDecisions to reduce noise and improve consistency.

The confidence computation is stateless, does not access databases, and never
mutates system state. It produces a ConfidenceScore summarizing the reliability
of an action decision based on market conditions, position metrics, and system health.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceScore:
    """Confidence score for an action decision.
    
    Attributes
    ----------
    symbol:
        Symbol for which confidence is computed.
    score:
        Confidence score (0-100). Higher is better.
    level:
        Confidence level: "HIGH" | "MEDIUM" | "LOW".
    factors:
        List of factors that contributed to the score (positive or negative).
    computed_at:
        Timestamp when this score was computed (ISO format).
    """
    symbol: str
    score: int  # 0-100
    level: str  # HIGH | MEDIUM | LOW
    factors: List[str] = field(default_factory=list)
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def compute_confidence(
    symbol: str,
    regime_confidence: int,
    price: Optional[float] = None,
    ema200: Optional[float] = None,
    dte: Optional[int] = None,
    premium_collected_pct: Optional[float] = None,
    system_health_status: Optional[str] = None,
) -> ConfidenceScore:
    """Compute confidence score for an action decision.
    
    This function is deterministic, stateless, and never mutates system state
    or accesses databases. It computes a confidence score based on various
    factors and returns a ConfidenceScore.
    
    Parameters
    ----------
    symbol:
        Symbol for which confidence is computed.
    regime_confidence:
        Regime confidence percentage (0-100).
    price:
        Current underlying price (optional).
    ema200:
        EMA200 value (optional).
    dte:
        Days to expiration (optional).
    premium_collected_pct:
        Premium collected percentage (0-100, optional).
    system_health_status:
        System health status: "HEALTHY" | "DEGRADED" | "HALT" (optional).
    
    Returns
    -------
    ConfidenceScore
        Confidence score with level, factors, and timestamp.
    
    Scoring Rules (starting at 50):
    --------------------------------
    1. +20 if regime_confidence >= 80
    2. +15 if price > ema200 (both must be provided)
    3. +10 if 7 <= dte <= 21
    4. +10 if premium_collected_pct >= 50
    5. -20 if system_health_status == "DEGRADED"
    6. -40 if system_health_status == "HALT"
    7. Clamp score to 0-100
    
    Level Mapping:
    --------------
    - score >= 75: HIGH
    - score 40-74: MEDIUM
    - score < 40: LOW
    """
    # Normalize system health status
    health_status_upper = system_health_status.upper() if system_health_status else None
    
    # Initialize score at 50
    score = 50
    factors: List[str] = []
    
    # Rule 1: +20 if regime_confidence >= 80
    if regime_confidence >= 80:
        score += 20
        factors.append(f"High regime confidence ({regime_confidence}%)")
    else:
        factors.append(f"Regime confidence {regime_confidence}%")
    
    # Rule 2: +15 if price > ema200 (both must be provided)
    if price is not None and ema200 is not None:
        if price > ema200:
            score += 15
            factors.append(f"Price ({price:.2f}) above EMA200 ({ema200:.2f})")
        else:
            factors.append(f"Price ({price:.2f}) below EMA200 ({ema200:.2f})")
    elif price is not None or ema200 is not None:
        factors.append("Incomplete price/EMA200 data")
    
    # Rule 3: +10 if 7 <= dte <= 21
    if dte is not None:
        if 7 <= dte <= 21:
            score += 10
            factors.append(f"Optimal DTE ({dte} days)")
        else:
            factors.append(f"DTE {dte} days (outside optimal 7-21 range)")
    
    # Rule 4: +10 if premium_collected_pct >= 50
    if premium_collected_pct is not None:
        if premium_collected_pct >= 50:
            score += 10
            factors.append(f"Premium collected {premium_collected_pct:.1f}%")
        else:
            factors.append(f"Premium collected {premium_collected_pct:.1f}% (below 50%)")
    
    # Rule 5: -20 if system_health_status == "DEGRADED"
    if health_status_upper == "DEGRADED":
        score -= 20
        factors.append("System health DEGRADED (-20)")
    
    # Rule 6: -40 if system_health_status == "HALT"
    if health_status_upper == "HALT":
        score -= 40
        factors.append("System health HALT (-40)")
    
    # Rule 7: Clamp score to 0-100
    score = max(0, min(100, score))
    
    # Level mapping
    if score >= 75:
        level = "HIGH"
    elif score >= 40:
        level = "MEDIUM"
    else:
        level = "LOW"
    
    # Build confidence score
    confidence_score = ConfidenceScore(
        symbol=symbol,
        score=score,
        level=level,
        factors=factors,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Log confidence score
    logger.info(
        f"ConfidenceEngine: {symbol} | score={score} | level={level} | "
        f"regime_conf={regime_confidence}% | health={health_status_upper or 'N/A'}"
    )
    
    return confidence_score


__all__ = ["ConfidenceScore", "compute_confidence"]
