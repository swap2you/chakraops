# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""CSP trade planning engine.

This module contains pure business logic for generating CSP trade plans.
No UI, alerts, or external integrations - only decision-making logic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from app.core.config.trade_rules import (
    CSP_MAX_DTE,
    CSP_MIN_DTE,
    CSP_TARGET_DELTA_HIGH,
    CSP_TARGET_DELTA_LOW,
    MAX_CAPITAL_PER_SYMBOL_PCT,
)
from app.core.engine.position_engine import PositionEngine

logger = logging.getLogger(__name__)


class CSPTradeEngine:
    """Engine for generating CSP trade plans from candidates."""

    def __init__(self, position_engine: Optional[PositionEngine] = None) -> None:
        """Create a new CSPTradeEngine."""
        self.position_engine = position_engine or PositionEngine()

    def generate_trade_plan(
        self,
        candidate: Dict[str, Any],
        portfolio_value: float,
        regime: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate a trade plan for a CSP candidate.

        Parameters
        ----------
        candidate:
            Candidate dictionary from wheel engine, containing:
            - symbol: str
            - contract: dict with expiry, strike, delta, premium_estimate (optional)
            - key_levels: dict with close, ema50, ema200, etc.
        portfolio_value:
            Total portfolio value in dollars.
        regime:
            Current market regime ("RISK_ON" or "RISK_OFF").

        Returns
        -------
        dict | None
            Trade plan dictionary with:
            - symbol: str
            - strike: float
            - expiry: str (ISO date YYYY-MM-DD)
            - contracts: int
            - estimated_premium: float
            - capital_required: float
            - rationale: list[str]

            Returns None if trade is blocked, with reason logged.
        """
        symbol = candidate.get("symbol", "").upper()
        if not symbol:
            logger.warning("Candidate missing symbol, cannot generate trade plan")
            return None

        rationale = []

        # Check market regime
        if regime.upper() != "RISK_ON":
            logger.info(f"Trade blocked for {symbol}: regime is {regime}, not RISK_ON")
            return None
        rationale.append(f"Market regime: {regime}")

        # Check for existing open position
        if self.position_engine.has_open_position(symbol):
            logger.info(f"Trade blocked for {symbol}: open position already exists")
            return None
        rationale.append("No existing open position")

        # Extract contract details from candidate
        contract = candidate.get("contract")
        if not contract:
            logger.info(f"Trade blocked for {symbol}: no contract details in candidate")
            return None

        strike = contract.get("strike")
        expiry = contract.get("expiry")
        premium_estimate = contract.get("premium_estimate")

        if strike is None or expiry is None:
            logger.info(f"Trade blocked for {symbol}: missing strike or expiry in contract")
            return None

        # Validate expiry is within DTE range
        try:
            expiry_date = datetime.fromisoformat(expiry).date()
            today = date.today()
            dte = (expiry_date - today).days

            if dte < CSP_MIN_DTE or dte > CSP_MAX_DTE:
                logger.info(
                    f"Trade blocked for {symbol}: DTE {dte} outside range "
                    f"[{CSP_MIN_DTE}, {CSP_MAX_DTE}]"
                )
                return None
            rationale.append(f"DTE: {dte} days (within {CSP_MIN_DTE}-{CSP_MAX_DTE} range)")

        except (ValueError, TypeError) as e:
            logger.warning(f"Trade blocked for {symbol}: invalid expiry format '{expiry}': {e}")
            return None

        # Validate delta if provided
        delta = contract.get("delta")
        if delta is not None:
            delta_abs = abs(float(delta))
            if delta_abs < CSP_TARGET_DELTA_LOW or delta_abs > CSP_TARGET_DELTA_HIGH:
                logger.info(
                    f"Trade blocked for {symbol}: delta {delta_abs:.3f} outside range "
                    f"[{CSP_TARGET_DELTA_LOW}, {CSP_TARGET_DELTA_HIGH}]"
                )
                return None
            rationale.append(f"Delta: {delta_abs:.3f} (within target range)")

        # Calculate contracts based on capital allocation
        strike_float = float(strike)
        max_capital = portfolio_value * MAX_CAPITAL_PER_SYMBOL_PCT
        capital_per_contract = strike_float * 100  # CSP requires 100 shares per contract

        if capital_per_contract > max_capital:
            logger.info(
                f"Trade blocked for {symbol}: capital per contract ${capital_per_contract:.2f} "
                f"exceeds max allocation ${max_capital:.2f}"
            )
            return None

        contracts = int(max_capital / capital_per_contract)
        if contracts < 1:
            logger.info(f"Trade blocked for {symbol}: cannot afford even 1 contract")
            return None

        # Calculate total capital required and estimated premium
        capital_required = contracts * capital_per_contract
        estimated_premium = (premium_estimate or 0.0) * contracts * 100 if premium_estimate else 0.0

        rationale.append(f"Capital allocation: ${capital_required:.2f} ({MAX_CAPITAL_PER_SYMBOL_PCT*100:.0f}% of portfolio)")
        rationale.append(f"Contracts: {contracts}")

        # Add candidate reasons if available
        candidate_reasons = candidate.get("reasons", [])
        if candidate_reasons:
            rationale.extend([f"Candidate: {r}" for r in candidate_reasons[:2]])  # Limit to first 2

        return {
            "symbol": symbol,
            "strike": strike_float,
            "expiry": expiry,
            "contracts": contracts,
            "estimated_premium": estimated_premium,
            "capital_required": capital_required,
            "rationale": rationale,
        }


__all__ = ["CSPTradeEngine"]
