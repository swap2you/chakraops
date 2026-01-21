# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Execution Guardrails for validating action decisions before execution.

This module provides a pure, deterministic validation layer that evaluates
ActionDecision objects and returns an ExecutionIntent indicating whether
execution is allowed or blocked.

The guard does NOT execute trades, integrate with broker APIs, or mutate
position state. It is a pure validation and permission layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.action_engine import ActionDecision
from app.core.models.position import Position
from app.core.state_machine import (
    PositionAction,
    PositionState,
    get_allowed_actions,
    next_state,
    validate_transition,
)
from app.core.system_health import SystemHealthSnapshot

logger = logging.getLogger(__name__)

# Default TTL for execution intents (15 minutes)
DEFAULT_TTL_MINUTES = 15


@dataclass
class ExecutionIntent:
    """Execution intent indicating whether an action is approved or blocked.
    
    Attributes
    ----------
    symbol:
        Position symbol.
    action:
        Action type: "HOLD" | "CLOSE" | "ROLL" | "ALERT".
    approved:
        True if execution is approved, False if blocked.
    blocked_reason:
        Reason why execution was blocked (None if approved).
    risk_flags:
        List of risk flags explaining why execution was blocked or approved.
    confidence:
        Confidence level: "HIGH" | "MEDIUM" | "LOW".
    computed_at:
        Timestamp when this intent was computed (ISO format).
    expires_at:
        Timestamp when this intent expires (ISO format, TTL from computed_at).
    """
    symbol: str
    action: str  # HOLD | CLOSE | ROLL | ALERT
    approved: bool
    blocked_reason: Optional[str] = None
    risk_flags: List[str] = field(default_factory=list)
    confidence: str = "MEDIUM"  # HIGH | MEDIUM | LOW
    computed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_TTL_MINUTES)).isoformat())


def evaluate_execution(
    action_decision: ActionDecision,
    position: Position,
    market_regime: str,
    ttl_minutes: int = DEFAULT_TTL_MINUTES,
    system_health: Optional[SystemHealthSnapshot] = None,
) -> ExecutionIntent:
    """Evaluate whether an action decision can be executed.
    
    This function is deterministic, stateless, and never mutates position state
    or accesses databases. It validates the action decision against guardrails
    and returns an ExecutionIntent.
    
    Parameters
    ----------
    action_decision:
        ActionDecision from the Action Engine.
    position:
        Position object. Must include:
        - symbol: str
        - state: str (current position state)
    market_regime:
        Market regime: "RISK_ON" | "RISK_OFF".
    ttl_minutes:
        Time-to-live for the execution intent in minutes (default: 15).
    system_health:
        Optional SystemHealthSnapshot. If provided and status == "HALT",
        execution will be blocked regardless of other rules.
    
    Returns
    -------
    ExecutionIntent
        Execution intent with approval status, risk flags, and expiration.
    
    Guard Rules (evaluated in order):
    ---------------------------------
    0. System Health HALT: Block ALL actions if system_health.status == "HALT"
    0.5. System Health DEGRADED: Add flag but allow execution
    1. Invalid inputs: Block with ERROR log
    2. State machine validation: Block if transition not allowed
    3. Regime blocking: Block OPEN/ROLL when regime == RISK_OFF
    4. Confidence blocking: Block CLOSE when confidence == LOW
    5. TTL enforcement: Set expires_at based on ttl_minutes
    6. Default: Approve if all checks pass
    """
    # Validate inputs
    if not action_decision:
        error_msg = "action_decision is None or invalid"
        logger.error(f"ExecutionGuard: {error_msg}")
        return ExecutionIntent(
            symbol=position.symbol if position else "UNKNOWN",
            action="UNKNOWN",
            approved=False,
            blocked_reason=error_msg,
            risk_flags=["INVALID_INPUT"],
            confidence="LOW",
        )
    
    if not position:
        error_msg = "position is None or invalid"
        logger.error(f"ExecutionGuard: {error_msg}")
        return ExecutionIntent(
            symbol=action_decision.symbol,
            action=action_decision.action,
            approved=False,
            blocked_reason=error_msg,
            risk_flags=["INVALID_INPUT"],
            confidence="LOW",
        )
    
    symbol = action_decision.symbol
    action = action_decision.action
    current_state_str = position.state or (position.status if hasattr(position, 'status') else 'OPEN')
    
    # Normalize market regime
    market_regime_upper = market_regime.upper() if market_regime else "RISK_OFF"
    
    # Compute timestamps
    computed_at = datetime.now(timezone.utc)
    expires_at = computed_at + timedelta(minutes=ttl_minutes)
    
    risk_flags: List[str] = []
    blocked_reason: Optional[str] = None
    approved = True
    confidence = "HIGH"
    
    # Rule 0: Global Kill Switch (System Health HALT)
    # This rule takes precedence over all other rules
    if system_health and system_health.status == "HALT":
        approved = False
        blocked_reason = "SYSTEM_HALTED: System health status is HALT"
        risk_flags.append("SYSTEM_HALTED")
        confidence = "HIGH"
        logger.warning(
            f"ExecutionGuard: {symbol} | {action} BLOCKED | {blocked_reason}"
        )
        # Build execution intent immediately (skip other rules)
        intent = ExecutionIntent(
            symbol=symbol,
            action=action,
            approved=approved,
            blocked_reason=blocked_reason,
            risk_flags=risk_flags,
            confidence=confidence,
            computed_at=computed_at.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        logger.warning(
            f"ExecutionGuard: {symbol} | {action} BLOCKED | reason={blocked_reason} | flags={risk_flags}"
        )
        return intent
    
    # Rule 0.5: System Degraded (allow execution but flag it)
    if system_health and system_health.status == "DEGRADED":
        risk_flags.append("SYSTEM_DEGRADED")
        # Continue with normal evaluation
    
    # Rule 1: State machine validation
    # Only validate transitions for actions that change state (not HOLD or ALERT)
    state_machine_blocked = False
    if action in ["CLOSE", "ROLL", "OPEN"]:
        try:
            # Map current state string to PositionState enum
            state_mapping = {
                "NEW": PositionState.NEW,
                "ASSIGNED": PositionState.ASSIGNED,
                "OPEN": PositionState.OPEN,
                "ROLLING": PositionState.ROLLING,
                "CLOSING": PositionState.CLOSING,
                "CLOSED": PositionState.CLOSED,
            }
            current_state_enum = state_mapping.get(current_state_str, PositionState.OPEN)
            
            # Map action string to PositionAction enum
            action_mapping = {
                "OPEN": PositionAction.OPEN,
                "CLOSE": PositionAction.CLOSE,
                "ROLL": PositionAction.ROLL,
                "HOLD": PositionAction.HOLD,
            }
            action_enum = action_mapping.get(action)
            
            if action_enum:
                # Check if transition is allowed
                allowed_actions = get_allowed_actions(current_state_enum)
                if action_enum not in allowed_actions:
                    approved = False
                    blocked_reason = f"State machine does not allow {action} from {current_state_str}"
                    risk_flags.append("STATE_MACHINE_BLOCKED")
                    confidence = "HIGH"
                    state_machine_blocked = True
                    logger.warning(
                        f"ExecutionGuard: {symbol} | {action} BLOCKED | {blocked_reason}"
                    )
                else:
                    risk_flags.append("STATE_MACHINE_VALIDATED")
        except Exception as e:
            # If state machine validation fails, log error but don't block
            # (graceful degradation)
            logger.error(f"ExecutionGuard: State machine validation error for {symbol}: {e}")
            risk_flags.append("STATE_MACHINE_VALIDATION_ERROR")
            confidence = "MEDIUM"
    
    # Rule 2: Regime blocking
    # Block OPEN and ROLL when market_regime == RISK_OFF
    # Skip if already blocked by state machine
    if not state_machine_blocked and action in ["OPEN", "ROLL"] and market_regime_upper == "RISK_OFF":
        approved = False
        blocked_reason = f"Market regime is RISK_OFF, blocking {action} action"
        risk_flags.append("REGIME_BLOCKED")
        confidence = "HIGH"
        logger.warning(
            f"ExecutionGuard: {symbol} | {action} BLOCKED | {blocked_reason}"
        )
    
    # Rule 3: Confidence blocking
    # Block CLOSE when confidence == LOW
    # Skip if already blocked by state machine
    if not state_machine_blocked and action == "CLOSE" and action_decision.urgency == "LOW":
        approved = False
        blocked_reason = "CLOSE action has LOW urgency/confidence, blocking execution"
        risk_flags.append("CONFIDENCE_BLOCKED")
        confidence = "MEDIUM"
        logger.warning(
            f"ExecutionGuard: {symbol} | {action} BLOCKED | {blocked_reason}"
        )
    
    # Rule 4: HOLD and ALERT actions are always approved (no execution needed)
    if action in ["HOLD", "ALERT"]:
        approved = True
        risk_flags.append("NO_EXECUTION_REQUIRED")
        confidence = "HIGH"
    
    # Build execution intent
    intent = ExecutionIntent(
        symbol=symbol,
        action=action,
        approved=approved,
        blocked_reason=blocked_reason,
        risk_flags=risk_flags,
        confidence=confidence,
        computed_at=computed_at.isoformat(),
        expires_at=expires_at.isoformat(),
    )
    
    # Log result
    if approved:
        logger.info(
            f"ExecutionGuard: {symbol} | {action} APPROVED | confidence={confidence} | flags={risk_flags}"
        )
    else:
        logger.warning(
            f"ExecutionGuard: {symbol} | {action} BLOCKED | reason={blocked_reason} | flags={risk_flags}"
        )
    
    return intent


__all__ = ["ExecutionIntent", "evaluate_execution", "DEFAULT_TTL_MINUTES"]
