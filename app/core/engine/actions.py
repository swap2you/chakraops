# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Action engine for determining position actions.

This module contains logic for deciding what action to take on a position
based on its current state and market context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from app.core.models.position import Position
from app.core.config.risk_overrides import (
    RISK_OFF_CLOSE_ENABLED,
    PANIC_DRAWDOWN_PCT,
    EMA200_BREAK_PCT,
)


class ActionType(Enum):
    """Types of actions that can be taken on a position."""
    
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    ROLL = "ROLL"
    ALERT = "ALERT"


class Urgency(Enum):
    """Urgency level for an action."""
    
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class RollPlan:
    """Plan for rolling a position to a new strike/expiry.
    
    Attributes
    ----------
    roll_type:
        Type of roll: "defensive" (if underlying < strike) or "out" (if underlying >= strike).
    suggested_expiry:
        Suggested expiration date for the roll (30-45 days from today).
    suggested_strike:
        Suggested strike price for the roll.
    notes:
        List of notes explaining the roll plan.
    """
    
    roll_type: str
    suggested_expiry: date
    suggested_strike: float
    notes: List[str] = field(default_factory=list)


@dataclass
class ActionDecision:
    """Represents a decision about what action to take on a position.
    
    Attributes
    ----------
    action:
        The type of action to take.
    urgency:
        The urgency level of the action.
    reasons:
        List of reasons for this decision.
    next_steps:
        List of suggested next steps.
    computed_at:
        Timestamp when this decision was computed.
    roll_plan:
        Optional roll plan (only populated when action == ROLL).
    """
    
    action: ActionType
    urgency: Urgency
    reasons: List[str]
    next_steps: List[str]
    computed_at: datetime
    roll_plan: Optional[RollPlan] = None


def decide_position_action(
    position: Position,
    market_ctx: Dict[str, Any],
) -> ActionDecision:
    """Decide what action to take on a position based on its state and market context.
    
    Parameters
    ----------
    position:
        The position to evaluate.
    market_ctx:
        Market context dictionary. May contain:
        - premium_collected_pct: float (optional, percentage of premium captured)
        - regime: str (optional, "RISK_ON" or "RISK_OFF")
        - underlying_price: float (optional, current stock price)
        - ema200: float (optional, 200-day EMA value)
        - entry_underlying_price: float (optional, price at position entry)
        - atr_pct: float (optional, ATR as percentage)
    
    Returns
    -------
    ActionDecision
        Decision object containing action type, urgency, reasons, and next steps.
    
    Rules (Priority Order)
    ----------------------
    Risk Overrides (Day3):
    - RISK_OFF regime handling
    - Panic drawdown threshold
    - EMA200 break detection
    
    Standard Rules (Day1):
    1. If position.state in {CLOSED, ASSIGNED} => HOLD (LOW)
    2. If DTE <= 7 => ROLL (HIGH)
    3. If premium_capture_pct >= 65% => CLOSE (MEDIUM)
    4. Else => HOLD (LOW)
    """
    # Get position state first
    position_state = position.state or (position.status if hasattr(position, 'status') else 'OPEN')
    
    # Rule 1: Check if position is in terminal/non-actionable state (highest priority)
    if position_state in ("CLOSED", "ASSIGNED"):
        return ActionDecision(
            action=ActionType.HOLD,
            urgency=Urgency.LOW,
            reasons=["Position not actionable"],
            next_steps=["No action required"],
            computed_at=datetime.now(),
        )
    
    # Risk Override 1: RISK_OFF regime handling (only for actionable positions)
    regime = market_ctx.get("regime", "").upper()
    
    if regime == "RISK_OFF":
        if RISK_OFF_CLOSE_ENABLED and position_state == "OPEN":
            return ActionDecision(
                action=ActionType.CLOSE,
                urgency=Urgency.HIGH,
                reasons=["RISK_OFF regime detected - automatic close enabled"],
                next_steps=[
                    "Close position immediately",
                    "Reduce overall portfolio exposure",
                ],
                computed_at=datetime.now(),
            )
        else:
            return ActionDecision(
                action=ActionType.ALERT,
                urgency=Urgency.HIGH,
                reasons=["RISK_OFF regime detected"],
                next_steps=[
                    "Reduce exposure / tighten rolls",
                    "Consider defensive positioning",
                    "Monitor market conditions closely",
                ],
                computed_at=datetime.now(),
            )
    
    # Risk Override 2: Panic drawdown threshold
    entry_price = market_ctx.get("entry_underlying_price")
    current_price = market_ctx.get("underlying_price")
    
    if entry_price is not None and current_price is not None and entry_price > 0:
        drawdown_pct = (entry_price - current_price) / entry_price
        if drawdown_pct >= PANIC_DRAWDOWN_PCT:
            return ActionDecision(
                action=ActionType.ALERT,
                urgency=Urgency.HIGH,
                reasons=[f"Panic drawdown threshold hit ({drawdown_pct*100:.1f}% >= {PANIC_DRAWDOWN_PCT*100:.0f}%)"],
                next_steps=[
                    "Consider defensive roll",
                    "Evaluate position risk vs reward",
                    "Review portfolio exposure",
                ],
                computed_at=datetime.now(),
            )
    
    # Risk Override 3: EMA200 break detection
    ema200 = market_ctx.get("ema200")
    if ema200 is not None and current_price is not None and ema200 > 0:
        ema200_break_threshold = ema200 * (1 - EMA200_BREAK_PCT)
        if current_price < ema200_break_threshold:
            return ActionDecision(
                action=ActionType.ALERT,
                urgency=Urgency.HIGH,
                reasons=[f"EMA200 break detected (price ${current_price:.2f} < ${ema200_break_threshold:.2f})"],
                next_steps=[
                    "Review position risk",
                    "Consider defensive actions",
                    "Monitor trend continuation",
                ],
                computed_at=datetime.now(),
            )
    
    # Rule 2: Check DTE (Days to Expiry)
    dte = None
    if position.expiry:
        try:
            # Try parsing as date first (YYYY-MM-DD format)
            if isinstance(position.expiry, str) and len(position.expiry) == 10:
                expiry_date = date.fromisoformat(position.expiry)
            else:
                # Try parsing as datetime and extract date
                expiry_date = datetime.fromisoformat(position.expiry).date()
            today = date.today()
            dte = (expiry_date - today).days
        except (ValueError, AttributeError, TypeError):
            dte = None
    
    if dte is not None and dte <= 7:
        # Build roll plan
        roll_plan = _build_roll_plan(position, market_ctx)
        
        return ActionDecision(
            action=ActionType.ROLL,
            urgency=Urgency.HIGH,
            reasons=["Expiry within 7 days"],
            next_steps=[
                "Consider rolling to new strike/expiry",
                "Evaluate roll credit vs assignment risk",
            ],
            computed_at=datetime.now(),
            roll_plan=roll_plan,
        )
    
    # Rule 3: Check premium capture percentage
    premium_capture_pct = market_ctx.get("premium_collected_pct")
    
    # Fallback: compute from position if not in market_ctx
    if premium_capture_pct is None:
        if position.strike and position.strike > 0 and position.contracts > 0:
            # Calculate premium per contract
            premium_per_contract = position.premium_collected / position.contracts
            # Premium capture % = (premium_collected / (strike * 100)) * 100
            premium_capture_pct = (premium_per_contract / (position.strike * 100)) * 100
        else:
            premium_capture_pct = 0.0
    
    # Compare as percentage (65.0), not decimal (0.65)
    if premium_capture_pct >= 65.0:
        return ActionDecision(
            action=ActionType.CLOSE,
            urgency=Urgency.MEDIUM,
            reasons=[f"Premium >= 65% captured ({premium_capture_pct:.1f}%)"],
            next_steps=[
                "Consider closing position to lock in profit",
                "Evaluate remaining time value vs profit target",
            ],
            computed_at=datetime.now(),
        )
    
    # Rule 4: Default to HOLD
    return ActionDecision(
        action=ActionType.HOLD,
        urgency=Urgency.LOW,
        reasons=["No action required at this time"],
        next_steps=["Continue monitoring position"],
        computed_at=datetime.now(),
    )


def _build_roll_plan(
    position: Position,
    market_ctx: Dict[str, Any],
) -> RollPlan:
    """Build a roll plan for a position.
    
    Parameters
    ----------
    position:
        The position to roll.
    market_ctx:
        Market context dictionary. May contain:
        - underlying_price: float (current stock price)
        - atr_pct: float (optional, ATR as percentage, default 0.03)
    
    Returns
    -------
    RollPlan
        Roll plan with suggested expiry, strike, and roll type.
    """
    today = date.today()
    
    # Calculate suggested expiry: today + 35 days (capped within 30-45 days)
    suggested_expiry = today + timedelta(days=35)
    # Ensure it's within 30-45 days window
    min_expiry = today + timedelta(days=30)
    max_expiry = today + timedelta(days=45)
    suggested_expiry = max(min_expiry, min(suggested_expiry, max_expiry))
    
    # Get underlying price from market context
    underlying_price = market_ctx.get("underlying_price")
    if underlying_price is None:
        # Fallback: use strike as proxy (not ideal, but better than nothing)
        underlying_price = position.strike or 0.0
    
    # Determine roll type
    if position.strike and underlying_price < position.strike:
        roll_type = "defensive"
    else:
        roll_type = "out"
    
    # Get ATR percentage (default 3%)
    atr_pct = market_ctx.get("atr_pct", 0.03)
    atr_proxy = underlying_price * atr_pct
    
    # Calculate suggested strike based on roll type
    if roll_type == "defensive":
        # Defensive: max(underlying_price * 0.90, underlying_price - 2*ATR_proxy)
        strike_option1 = underlying_price * 0.90
        strike_option2 = underlying_price - (2 * atr_proxy)
        suggested_strike = max(strike_option1, strike_option2)
        notes = [
            f"Defensive roll: underlying ${underlying_price:.2f} below strike ${position.strike:.2f}",
            f"Suggested strike ${suggested_strike:.2f} provides downside protection",
        ]
    else:  # roll_type == "out"
        # Out: underlying_price * 0.95
        suggested_strike = underlying_price * 0.95
        notes = [
            f"Out roll: underlying ${underlying_price:.2f} at or above strike ${position.strike:.2f}",
            f"Suggested strike ${suggested_strike:.2f} collects premium while maintaining upside",
        ]
    
    # Round strike to nearest $0.50 (standard option strike spacing)
    suggested_strike = round(suggested_strike * 2) / 2.0
    
    return RollPlan(
        roll_type=roll_type,
        suggested_expiry=suggested_expiry,
        suggested_strike=suggested_strike,
        notes=notes,
    )


__all__ = ["ActionType", "Urgency", "ActionDecision", "RollPlan", "decide_position_action"]
