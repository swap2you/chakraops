# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Risk evaluation engine for open positions.

This module contains pure business logic for evaluating position risk.
No UI, alerts, or external integrations - only decision-making logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal

from app.core.models.position import Position

logger = logging.getLogger(__name__)

Status = Literal["HOLD", "PREPARE_ROLL", "ACTION_REQUIRED"]


class RiskEngine:
    """Engine for evaluating risk and status of open positions."""

    def evaluate_position(
        self,
        position: Position,
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate a position and return risk status.

        Parameters
        ----------
        position:
            Position to evaluate.
        market_context:
            Dictionary containing:
            - regime: str ("RISK_ON" or "RISK_OFF")
            - current_price: float (current stock price)
            - ema200: float (200-day EMA)
            - delta: Optional[float] (current option delta, if available)
            - strike: float (option strike price, if CSP)

        Returns
        -------
        dict
            Evaluation result with:
            - symbol: str
            - status: "HOLD" | "PREPARE_ROLL" | "ACTION_REQUIRED"
            - reasons: list[str]
            - premium_pct: float (premium collected as % of strike)
        """
        symbol = position.symbol.upper()
        reasons = []
        status: Status = "HOLD"

        # Extract market context
        regime = market_context.get("regime", "").upper()
        current_price = market_context.get("current_price")
        ema200 = market_context.get("ema200")
        delta = market_context.get("delta")
        strike = position.strike or market_context.get("strike")

        # Calculate premium percentage
        premium_pct = 0.0
        if strike and strike > 0:
            # Premium collected per contract (premium_collected is total for all contracts)
            premium_per_contract = position.premium_collected / position.contracts if position.contracts > 0 else 0
            premium_pct = (premium_per_contract / (strike * 100)) * 100 if strike > 0 else 0.0

        # Rule 1: ACTION_REQUIRED conditions (highest priority)
        action_required = False

        # Price below EMA200
        if current_price is not None and ema200 is not None:
            if current_price < ema200:
                action_required = True
                reasons.append(f"Price ${current_price:.2f} below EMA200 ${ema200:.2f}")

        # Regime is RISK_OFF
        if regime == "RISK_OFF":
            action_required = True
            reasons.append("Market regime is RISK_OFF")

        # Premium >= 75%
        if premium_pct >= 75.0:
            action_required = True
            reasons.append(f"Premium collected {premium_pct:.1f}% >= 75% (take profit)")

        if action_required:
            status = "ACTION_REQUIRED"
            return {
                "symbol": symbol,
                "status": status,
                "reasons": reasons,
                "premium_pct": premium_pct,
            }

        # Rule 2: PREPARE_ROLL conditions
        prepare_roll = False

        # Premium >= 50%
        if premium_pct >= 50.0:
            prepare_roll = True
            reasons.append(f"Premium collected {premium_pct:.1f}% >= 50% (consider rolling)")

        # Delta > 0.45 (for puts, this means getting close to assignment)
        if delta is not None:
            delta_abs = abs(float(delta))
            if delta_abs > 0.45:
                prepare_roll = True
                reasons.append(f"Delta {delta_abs:.2f} > 0.45 (increasing assignment risk)")

        if prepare_roll:
            status = "PREPARE_ROLL"
            return {
                "symbol": symbol,
                "status": status,
                "reasons": reasons,
                "premium_pct": premium_pct,
            }

        # Rule 3: HOLD (default)
        # Premium < 50% and price > EMA200
        if current_price is not None and ema200 is not None:
            if current_price > ema200:
                reasons.append(f"Price ${current_price:.2f} above EMA200 ${ema200:.2f}")
        reasons.append(f"Premium collected {premium_pct:.1f}% < 50%")

        return {
            "symbol": symbol,
            "status": status,
            "reasons": reasons,
            "premium_pct": premium_pct,
        }


__all__ = ["RiskEngine", "Status"]
