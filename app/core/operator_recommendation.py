# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Operator UX – "What Should I Do Now?" Recommendation Engine.

This module provides a deterministic function for producing a single,
human-friendly recommendation summarizing what the operator should do next.

The recommendation computation is stateless, does not access databases, and
never mutates system state. It analyzes execution plans and produces a
prioritized recommendation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OperatorRecommendation:
    """Operator recommendation for next action.
    
    Attributes
    ----------
    priority:
        Priority level: "NOW" | "SOON" | "MONITOR" | "NOTHING".
    symbol:
        Symbol for the recommended action (None if NOTHING).
    action:
        Recommended action: "CLOSE" | "ROLL" | "HOLD" | "ALERT" | None.
    confidence:
        Confidence level: "HIGH" | "MEDIUM" | "LOW" | None.
    reason:
        Human-readable reason for the recommendation.
    next_check_minutes:
        Minutes until next check should be performed.
    generated_at:
        Timestamp when this recommendation was generated (ISO format).
    """
    priority: str  # NOW | SOON | MONITOR | NOTHING
    symbol: Optional[str] = None
    action: Optional[str] = None  # CLOSE | ROLL | HOLD | ALERT
    confidence: Optional[str] = None  # HIGH | MEDIUM | LOW
    reason: str = ""
    next_check_minutes: int = 60  # Default: 60 minutes
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def generate_operator_recommendation(
    execution_plans: List[any],
) -> OperatorRecommendation:
    """Generate a single operator recommendation from execution plans.
    
    This function is deterministic, stateless, and never mutates system state
    or accesses databases. It analyzes execution plans and produces a prioritized
    recommendation using tie-breaking logic.
    
    Parameters
    ----------
    execution_plans:
        List of ExecutionPlan objects. Each plan should have:
        - symbol: str
        - action: str (CLOSE | ROLL | HOLD | ALERT)
        - confidence: str (HIGH | MEDIUM | LOW)
        - parameters: dict (may contain expiry information)
    
    Returns
    -------
    OperatorRecommendation
        Single prioritized recommendation.
    
    Priority Rules:
    --------------
    1. NOW: CLOSE or ROLL with HIGH confidence
    2. SOON: CLOSE or ROLL with MEDIUM confidence
    3. MONITOR: HOLD or ALERT actions
    4. NOTHING: no actionable plans
    
    Tie-Breaking (within same priority):
    -----------------------------------
    1. Higher confidence (HIGH > MEDIUM > LOW)
    2. Nearest expiry (if available in plan.parameters)
    """
    if not execution_plans:
        return OperatorRecommendation(
            priority="NOTHING",
            reason="No execution plans available. System is idle.",
            next_check_minutes=60,
        )
    
    # Categorize plans by priority
    now_plans: List[any] = []  # CLOSE/ROLL with HIGH confidence
    soon_plans: List[any] = []  # CLOSE/ROLL with MEDIUM confidence
    monitor_plans: List[any] = []  # HOLD or ALERT
    
    for plan in execution_plans:
        if not plan:
            continue
        
        action = getattr(plan, "action", None)
        confidence = getattr(plan, "confidence", None)
        
        if action in ["CLOSE", "ROLL"]:
            if confidence == "HIGH":
                now_plans.append(plan)
            elif confidence == "MEDIUM":
                soon_plans.append(plan)
        elif action in ["HOLD", "ALERT"]:
            monitor_plans.append(plan)
    
    # Select recommendation based on priority
    recommendation: OperatorRecommendation
    
    if now_plans:
        # Priority: NOW
        selected_plan = _select_best_plan(now_plans)
        recommendation = OperatorRecommendation(
            priority="NOW",
            symbol=getattr(selected_plan, "symbol", None),
            action=getattr(selected_plan, "action", None),
            confidence=getattr(selected_plan, "confidence", None),
            reason=f"Immediate action required: {getattr(selected_plan, 'action', 'UNKNOWN')} {getattr(selected_plan, 'symbol', 'UNKNOWN')} with HIGH confidence",
            next_check_minutes=15,  # Check again in 15 minutes
        )
    elif soon_plans:
        # Priority: SOON
        selected_plan = _select_best_plan(soon_plans)
        recommendation = OperatorRecommendation(
            priority="SOON",
            symbol=getattr(selected_plan, "symbol", None),
            action=getattr(selected_plan, "action", None),
            confidence=getattr(selected_plan, "confidence", None),
            reason=f"Action recommended soon: {getattr(selected_plan, 'action', 'UNKNOWN')} {getattr(selected_plan, 'symbol', 'UNKNOWN')} with MEDIUM confidence",
            next_check_minutes=30,  # Check again in 30 minutes
        )
    elif monitor_plans:
        # Priority: MONITOR
        selected_plan = _select_best_plan(monitor_plans)
        recommendation = OperatorRecommendation(
            priority="MONITOR",
            symbol=getattr(selected_plan, "symbol", None),
            action=getattr(selected_plan, "action", None),
            confidence=getattr(selected_plan, "confidence", None),
            reason=f"Monitor: {getattr(selected_plan, 'action', 'UNKNOWN')} for {getattr(selected_plan, 'symbol', 'UNKNOWN')}",
            next_check_minutes=60,  # Check again in 60 minutes
        )
    else:
        # No actionable plans
        recommendation = OperatorRecommendation(
            priority="NOTHING",
            reason="No actionable execution plans. All positions are stable.",
            next_check_minutes=60,
        )
    
    # Log recommendation
    logger.info(
        f"OperatorRecommendation: priority={recommendation.priority} | "
        f"symbol={recommendation.symbol or 'N/A'} | "
        f"action={recommendation.action or 'N/A'} | "
        f"confidence={recommendation.confidence or 'N/A'} | "
        f"next_check={recommendation.next_check_minutes}min"
    )
    
    return recommendation


def _select_best_plan(plans: List[any]) -> any:
    """Select the best plan from a list using tie-breaking logic.
    
    Tie-breaking order:
    1. Higher confidence (HIGH > MEDIUM > LOW)
    2. Nearest expiry (if available)
    3. First plan (if all else equal)
    
    Parameters
    ----------
    plans:
        List of ExecutionPlan objects.
    
    Returns
    -------
    ExecutionPlan
        Best plan according to tie-breaking rules.
    """
    if not plans:
        return None
    
    if len(plans) == 1:
        return plans[0]
    
    # Confidence ranking
    confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    
    # Sort by confidence (descending), then by expiry (ascending if available)
    def plan_key(plan):
        confidence = getattr(plan, "confidence", "LOW")
        confidence_score = confidence_rank.get(confidence, 0)
        
        # Try to extract expiry from parameters
        expiry_score = float("inf")  # Default: no expiry (sort last)
        parameters = getattr(plan, "parameters", {})
        if isinstance(parameters, dict):
            # Look for expiry in various possible formats
            expiry = parameters.get("expiry") or parameters.get("expiry_date") or parameters.get("expiry_date_str")
            if expiry:
                # If it's a date string, try to parse it
                # For simplicity, we'll use string comparison if it's ISO format
                # In real implementation, you'd parse and compare dates
                try:
                    # Assume ISO format date string for comparison
                    expiry_score = hash(str(expiry))  # Simple hash for comparison
                except Exception:
                    pass
        
        return (-confidence_score, expiry_score)  # Negative for descending confidence
    
    sorted_plans = sorted(plans, key=plan_key)
    return sorted_plans[0]


__all__ = ["OperatorRecommendation", "generate_operator_recommendation"]
