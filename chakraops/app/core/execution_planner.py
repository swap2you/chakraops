# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Execution Planner for translating approved ExecutionIntent into ExecutionPlan.

This module provides a pure, deterministic planning layer that translates
approved ExecutionIntent objects into detailed ExecutionPlan objects.

The planner does NOT execute trades, integrate with broker APIs, or mutate
position state. It is a pure planning layer with no side effects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.execution_guard import ExecutionIntent

logger = logging.getLogger(__name__)


class ExecutionPlanBlockedError(Exception):
    """Raised when attempting to plan execution for a blocked intent."""
    
    def __init__(self, symbol: str, action: str, blocked_reason: Optional[str] = None):
        self.symbol = symbol
        self.action = action
        self.blocked_reason = blocked_reason
        message = f"Cannot plan execution for {symbol} | {action}"
        if blocked_reason:
            message += f": {blocked_reason}"
        super().__init__(message)


@dataclass
class ExecutionPlan:
    """Execution plan for an approved action.
    
    Attributes
    ----------
    symbol:
        Position symbol.
    action:
        Action type: "HOLD" | "CLOSE" | "ROLL" | "ALERT".
    steps:
        List of execution steps (ordered sequence).
    parameters:
        Dictionary of execution parameters (pricing, quantities, etc.).
    risk_notes:
        List of risk-related notes and warnings.
    confidence:
        Confidence level: "HIGH" | "MEDIUM" | "LOW".
    created_at:
        Timestamp when this plan was created (ISO format).
    """
    symbol: str
    action: str  # HOLD | CLOSE | ROLL | ALERT
    steps: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_notes: List[str] = field(default_factory=list)
    confidence: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def plan_execution(execution_intent: ExecutionIntent) -> ExecutionPlan:
    """Plan execution for an approved ExecutionIntent.
    
    This function is deterministic, stateless, and never mutates position state
    or accesses databases. It translates an approved ExecutionIntent into a
    detailed ExecutionPlan.
    
    Parameters
    ----------
    execution_intent:
        ExecutionIntent object. Must have approved == True.
    
    Returns
    -------
    ExecutionPlan
        Detailed execution plan with steps, parameters, and risk notes.
    
    Raises
    ------
    ExecutionPlanBlockedError
        If execution_intent.approved == False.
    ValueError
        If execution_intent is None or invalid.
    
    Action Mappings:
    ----------------
    - HOLD → no-op plan (no execution steps)
    - CLOSE → buy-to-close plan with limit/MID pricing
    - ROLL → buy-to-close + sell-to-open with roll parameters
    - ALERT → notification-only plan (no execution steps)
    """
    # Validate input
    if not execution_intent:
        error_msg = "execution_intent is None or invalid"
        logger.error(f"ExecutionPlanner: {error_msg}")
        raise ValueError(error_msg)
    
    # Check if execution is approved
    if not execution_intent.approved:
        error_msg = f"Execution intent is not approved for {execution_intent.symbol} | {execution_intent.action}"
        if execution_intent.blocked_reason:
            error_msg += f": {execution_intent.blocked_reason}"
        logger.warning(f"ExecutionPlanner: {error_msg}")
        raise ExecutionPlanBlockedError(
            execution_intent.symbol,
            execution_intent.action,
            execution_intent.blocked_reason,
        )
    
    symbol = execution_intent.symbol
    action = execution_intent.action
    confidence = execution_intent.confidence
    
    # Create base plan
    plan = ExecutionPlan(
        symbol=symbol,
        action=action,
        confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    
    # Map action to execution plan
    if action == "HOLD":
        plan = _plan_hold(plan, execution_intent)
    elif action == "CLOSE":
        plan = _plan_close(plan, execution_intent)
    elif action == "ROLL":
        plan = _plan_roll(plan, execution_intent)
    elif action == "ALERT":
        plan = _plan_alert(plan, execution_intent)
    else:
        # Unknown action type
        plan.risk_notes.append(f"Unknown action type: {action}")
        plan.confidence = "LOW"
        logger.warning(f"ExecutionPlanner: Unknown action type {action} for {symbol}")
    
    logger.info(
        f"ExecutionPlanner: {symbol} | {action} PLAN CREATED | steps={len(plan.steps)} | confidence={plan.confidence}"
    )
    
    return plan


def _plan_hold(plan: ExecutionPlan, intent: ExecutionIntent) -> ExecutionPlan:
    """Plan HOLD action (no-op)."""
    plan.steps = [
        "No execution required",
        "Continue monitoring position",
    ]
    plan.parameters = {
        "execution_type": "NO_OP",
    }
    plan.risk_notes = [
        "HOLD action requires no execution",
        "Position remains unchanged",
    ]
    plan.confidence = "HIGH"
    return plan


def _plan_close(plan: ExecutionPlan, intent: ExecutionIntent) -> ExecutionPlan:
    """Plan CLOSE action (buy-to-close)."""
    plan.steps = [
        "1. Calculate current option price (MID = (bid + ask) / 2)",
        "2. Set limit price at MID or slightly above (MID + 0.05)",
        "3. Place buy-to-close order",
        "4. Monitor order fill",
        "5. Update position state to CLOSING after fill",
    ]
    plan.parameters = {
        "execution_type": "BUY_TO_CLOSE",
        "pricing_strategy": "LIMIT_AT_MID",
        "limit_price_offset": 0.05,  # $0.05 above MID
        "order_type": "LIMIT",
        "time_in_force": "DAY",
    }
    plan.risk_notes = [
        "Buy-to-close order may not fill if market moves against limit price",
        "Consider market order if immediate execution is required",
        "Verify position state before placing order",
    ]
    plan.confidence = intent.confidence
    return plan


def _plan_roll(plan: ExecutionPlan, intent: ExecutionIntent) -> ExecutionPlan:
    """Plan ROLL action (buy-to-close + sell-to-open)."""
    plan.steps = [
        "1. Calculate current option price (MID = (bid + ask) / 2) for existing position",
        "2. Set buy-to-close limit price at MID or slightly above (MID + 0.05)",
        "3. Calculate new option strike and expiry based on roll parameters",
        "4. Calculate new option price (MID) for new position",
        "5. Set sell-to-open limit price at MID or slightly below (MID - 0.05)",
        "6. Place buy-to-close order",
        "7. After fill, place sell-to-open order",
        "8. Monitor both orders",
        "9. Update position state to ROLLING after buy-to-close fill",
        "10. Update position state to OPEN after sell-to-open fill",
    ]
    plan.parameters = {
        "execution_type": "ROLL",
        "leg1_type": "BUY_TO_CLOSE",
        "leg1_pricing_strategy": "LIMIT_AT_MID",
        "leg1_limit_price_offset": 0.05,  # $0.05 above MID
        "leg2_type": "SELL_TO_OPEN",
        "leg2_pricing_strategy": "LIMIT_AT_MID",
        "leg2_limit_price_offset": -0.05,  # $0.05 below MID
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "roll_net_credit_target": "POSITIVE",  # Aim for net credit
    }
    plan.risk_notes = [
        "Roll requires two-leg execution (buy-to-close + sell-to-open)",
        "Both orders must fill for successful roll",
        "Net credit may be negative if market moves between legs",
        "Consider using spread order if broker supports it",
        "Verify position state transitions: OPEN -> ROLLING -> OPEN",
    ]
    plan.confidence = intent.confidence
    return plan


def _plan_alert(plan: ExecutionPlan, intent: ExecutionIntent) -> ExecutionPlan:
    """Plan ALERT action (notification-only)."""
    plan.steps = [
        "1. Generate alert notification",
        "2. Log alert to database",
        "3. Send notification to configured channels (Slack, email, etc.)",
        "4. No position execution required",
    ]
    plan.parameters = {
        "execution_type": "NOTIFICATION_ONLY",
        "notification_channels": ["DATABASE", "SLACK"],
    }
    plan.risk_notes = [
        "ALERT action requires no position execution",
        "Alert should be reviewed by trader",
        "Position remains unchanged",
    ]
    plan.confidence = "HIGH"
    return plan


__all__ = ["ExecutionPlan", "ExecutionPlanBlockedError", "plan_execution"]
