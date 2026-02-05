# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Action Engine for deterministic position action evaluation.

This module provides a pure, deterministic function for evaluating OPEN positions
and returning exactly one action decision: HOLD | CLOSE | ROLL | ALERT.

The engine is stateless, does not access databases, and never mutates position state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List

from app.core.models.position import Position

logger = logging.getLogger(__name__)


@dataclass
class ActionDecision:
    """Action decision for a position.
    
    Attributes
    ----------
    symbol:
        Position symbol.
    action:
        Action to take: "HOLD" | "CLOSE" | "ROLL" | "ALERT".
    urgency:
        Urgency level: "LOW" | "MEDIUM" | "HIGH".
    reason_codes:
        List of reason codes explaining the decision.
    explanation:
        Human-readable explanation of the decision.
    allowed_next_states:
        List of allowed next states based on current position state.
    """
    symbol: str
    action: str  # HOLD | CLOSE | ROLL | ALERT
    urgency: str  # LOW | MEDIUM | HIGH
    reason_codes: List[str]
    explanation: str
    allowed_next_states: List[str]


def evaluate_position_action(
    position: Position,
    market_context: Dict[str, Any],
) -> ActionDecision:
    """Evaluate a position and return exactly one action decision.
    
    This function is deterministic, stateless, and never mutates position state
    or accesses databases. It evaluates rules in priority order (first match wins).
    
    Parameters
    ----------
    position:
        Position object. Must include:
        - symbol: str
        - state: str (should be "OPEN" for evaluation)
        - strike: float | None
        - expiry: str | None (ISO date format)
        - premium_collected_pct: float | None (percentage, e.g., 70.0 for 70%)
    market_context:
        Dictionary containing:
        - price: float (current underlying price)
        - EMA50: float | None (50-day EMA)
        - EMA200: float | None (200-day EMA)
        - ATR_pct: float | None (ATR as percentage, e.g., 0.03 for 3%)
        - regime: str | None ("RISK_ON" | "RISK_OFF")
    
    Returns
    -------
    ActionDecision
        Exactly one action decision with all fields populated.
    
    Rules (evaluated in order, first match wins):
    -------------------------------------------------
    0. StopEngine (formal exit plan): profit target, max loss, time stop,
       underlying breach, regime flip -> CLOSE or HOLD.
    1. CLOSE:
       - premium_collected_pct >= 70
       OR
       - DTE <= 3 AND premium_collected_pct >= 50
    
    2. ROLL:
       - DTE <= 7
       - premium_collected_pct < 50
       - price > EMA50
    
    3. ALERT:
       - price < EMA200
       OR
       - regime == "RISK_OFF"
    
    4. HOLD (default):
       - All other cases
    """
    # 0. Formal exit rules (StopEngine) first
    from app.core.exit.stop_engine import evaluate_stop
    stop_decision = evaluate_stop(position, market_context)
    if stop_decision.action != "HOLD":
        logger.info(
            f"ActionDecision (stop): {position.symbol} → {stop_decision.action} ({stop_decision.urgency}) | reasons={stop_decision.reason_codes}"
        )
        return stop_decision

    symbol = position.symbol
    current_state = position.state or (position.status if hasattr(position, 'status') else 'OPEN')
    
    # Calculate DTE (Days to Expiry)
    dte = None
    if position.expiry:
        try:
            if isinstance(position.expiry, str) and len(position.expiry) == 10:
                expiry_date = date.fromisoformat(position.expiry)
            else:
                expiry_date = datetime.fromisoformat(position.expiry).date()
            today = date.today()
            dte = (expiry_date - today).days
        except (ValueError, AttributeError, TypeError):
            dte = None
    
    # Extract market context values
    price = market_context.get("price")
    ema50 = market_context.get("EMA50")
    ema200 = market_context.get("EMA200")
    regime = market_context.get("regime", "").upper() if market_context.get("regime") else None
    
    # Get premium collected percentage
    premium_collected_pct = getattr(position, 'premium_collected_pct', None)
    if premium_collected_pct is None:
        premium_collected_pct = market_context.get("premium_collected_pct")
    
    # Calculate premium_collected_pct from position if not provided
    if premium_collected_pct is None:
        if position.strike and position.strike > 0 and position.contracts > 0:
            premium_per_contract = position.premium_collected / position.contracts
            # Premium capture % = (premium_collected / (strike * 100)) * 100
            premium_collected_pct = (premium_per_contract / (position.strike * 100)) * 100
        else:
            premium_collected_pct = 0.0
    
    # Determine allowed next states based on current state
    from app.core.state_machine import PositionState, get_allowed_actions
    try:
        state_mapping = {
            "NEW": PositionState.NEW,
            "ASSIGNED": PositionState.ASSIGNED,
            "OPEN": PositionState.OPEN,
            "ROLLING": PositionState.ROLLING,
            "CLOSING": PositionState.CLOSING,
            "CLOSED": PositionState.CLOSED,
        }
        current_state_enum = state_mapping.get(current_state, PositionState.OPEN)
        allowed_actions = get_allowed_actions(current_state_enum)
        allowed_next_states = [
            "OPEN" if a.value == "OPEN" else
            "CLOSING" if a.value == "CLOSE" else
            "ROLLING" if a.value == "ROLL" else
            current_state
            for a in allowed_actions
        ]
        # Add current state if HOLD is allowed (idempotent)
        if any(a.value == "HOLD" for a in allowed_actions):
            allowed_next_states.append(current_state)
        allowed_next_states = list(set(allowed_next_states))  # Remove duplicates
    except Exception:
        # Fallback if state machine not available
        allowed_next_states = ["OPEN", "CLOSING", "ROLLING"]
    
    # Rule 1: CLOSE
    # - premium_collected_pct >= 70
    # OR
    # - DTE <= 3 AND premium_collected_pct >= 50
    if premium_collected_pct >= 70.0:
        decision = ActionDecision(
            symbol=symbol,
            action="CLOSE",
            urgency="MEDIUM",
            reason_codes=["PREMIUM_70_PCT"],
            explanation=f"Premium collected {premium_collected_pct:.1f}% >= 70% threshold. Consider closing to lock in profit.",
            allowed_next_states=allowed_next_states,
        )
        logger.info(
            f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
        )
        return decision
    
    if dte is not None and dte <= 3 and premium_collected_pct >= 50.0:
        decision = ActionDecision(
            symbol=symbol,
            action="CLOSE",
            urgency="HIGH",
            reason_codes=["DTE_LE_3", "PREMIUM_50_PCT"],
            explanation=f"DTE {dte} <= 3 days and premium collected {premium_collected_pct:.1f}% >= 50%. Close to avoid assignment risk.",
            allowed_next_states=allowed_next_states,
        )
        logger.info(
            f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
        )
        return decision
    
    # Rule 2: ROLL
    # - DTE <= 7
    # - premium_collected_pct < 50
    # - price > EMA50
    if dte is not None and dte <= 7:
        if premium_collected_pct < 50.0:
            if price is not None and ema50 is not None and price > ema50:
                decision = ActionDecision(
                    symbol=symbol,
                    action="ROLL",
                    urgency="HIGH",
                    reason_codes=["DTE_LE_7", "PREMIUM_LT_50", "PRICE_GT_EMA50"],
                    explanation=f"DTE {dte} <= 7 days, premium {premium_collected_pct:.1f}% < 50%, and price ${price:.2f} > EMA50 ${ema50:.2f}. Consider rolling to extend position.",
                    allowed_next_states=allowed_next_states,
                )
                logger.info(
                    f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
                )
                return decision
    
    # Rule 3: ALERT
    # - price < EMA200
    # OR
    # - regime == "RISK_OFF"
    if price is not None and ema200 is not None and price < ema200:
        decision = ActionDecision(
            symbol=symbol,
            action="ALERT",
            urgency="HIGH",
            reason_codes=["PRICE_LT_EMA200"],
            explanation=f"Price ${price:.2f} < EMA200 ${ema200:.2f}. Trend may be weakening. Review position risk.",
            allowed_next_states=allowed_next_states,
        )
        logger.info(
            f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
        )
        return decision
    
    if regime == "RISK_OFF":
        decision = ActionDecision(
            symbol=symbol,
            action="ALERT",
            urgency="HIGH",
            reason_codes=["REGIME_RISK_OFF"],
            explanation="Market regime is RISK_OFF. Reduce exposure and review all positions.",
            allowed_next_states=allowed_next_states,
        )
        logger.info(
            f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
        )
        return decision
    
    # Rule 4: HOLD (default)
    decision = ActionDecision(
        symbol=symbol,
        action="HOLD",
        urgency="LOW",
        reason_codes=["DEFAULT"],
        explanation="No action required. Position is within acceptable parameters. Continue monitoring.",
        allowed_next_states=allowed_next_states,
    )
    
    # Log the decision
    logger.info(
        f"ActionDecision: {symbol} → {decision.action} ({decision.urgency}) | reasons={decision.reason_codes}"
    )
    
    return decision


__all__ = ["ActionDecision", "evaluate_position_action"]
