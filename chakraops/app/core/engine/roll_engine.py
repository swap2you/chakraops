# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Roll engine for suggesting position rolls.

This module contains pure business logic for suggesting roll strategies.
No UI, alerts, or external integrations - only decision-making logic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from app.core.engine.risk_engine import RiskEngine
from app.core.models.position import Position

logger = logging.getLogger(__name__)


class RollEngine:
    """Engine for suggesting roll strategies for open positions."""

    def __init__(self, orats_client: Optional[Any] = None):
        """Initialize roll engine.
        
        Parameters
        ----------
        orats_client:
            Optional OratsClient instance for fetching options chains.
            If None, roll suggestions will not be available.
        """
        self.risk_engine = RiskEngine()
        self.orats_client = orats_client

    def suggest_roll(
        self,
        position: Position,
        market_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Suggest a roll strategy for a position.
        
        Parameters
        ----------
        position:
            Position to evaluate for rolling.
        market_context:
            Dictionary containing:
            - regime: str ("RISK_ON" or "RISK_OFF")
            - current_price: float (current stock price)
            - ema200: float (200-day EMA)
            - ema50: Optional[float] (50-day EMA, will be calculated if not provided)
            - price_df: Optional[pd.DataFrame] (price data for calculating EMA50)
            - delta: Optional[float] (current option delta)
        
        Returns
        -------
        dict | None
            Roll suggestion with:
            - symbol: str
            - current_strike: float
            - current_expiry: str
            - suggested_strike: float
            - suggested_expiry: str
            - estimated_net_credit: float
            - reasons: list[str]
            
            Returns None if:
            - Position is not ACTION_REQUIRED
            - No suitable roll found
            - ORATS client unavailable
        """
        # Only suggest roll for CSP positions
        if position.position_type != "CSP":
            return None
        
        if not position.strike or not position.expiry:
            return None
        
        # Check if position is ACTION_REQUIRED
        evaluation = self.risk_engine.evaluate_position(position, market_context)
        if evaluation["status"] != "ACTION_REQUIRED":
            return None
        
        # Need ORATS client to fetch options chain
        if self.orats_client is None:
            return None
        
        # Get EMA50 from market context or calculate it
        ema50 = market_context.get("ema50")
        if ema50 is None:
            # Try to calculate from price_df
            price_df = market_context.get("price_df")
            if price_df is not None and not price_df.empty:
                try:
                    price_df = price_df.sort_values("date", ascending=True).reset_index(drop=True)
                    price_df["ema50"] = price_df["close"].ewm(span=50, adjust=False).mean()
                    ema50 = float(price_df.iloc[-1]["ema50"])
                except Exception as e:
                    logger.warning(f"Failed to calculate EMA50: {e}")
                    return None
            else:
                return None
        
        # Fetch options chain
        try:
            chain = self.orats_client.get_chain(position.symbol)
        except Exception as e:
            logger.warning(f"Failed to fetch options chain for {position.symbol}: {e}")
            return None
        
        if not chain:
            return None
        
        # Parse current expiry
        try:
            current_expiry = datetime.fromisoformat(position.expiry).date()
        except (ValueError, AttributeError):
            return None
        
        today = date.today()
        current_dte = (current_expiry - today).days
        
        # Calculate cost to close current position
        # Estimate: use mid price of current strike/expiry from chain
        current_close_cost = 0.0
        for contract in chain:
            try:
                expiry_raw = contract.get("expiry") or contract.get("expirationDate") or contract.get("expDate")
                expiry_date = self._parse_expiry(expiry_raw)
                if expiry_date != current_expiry:
                    continue
                
                strike = float(contract.get("strike") or contract.get("strikePrice"))
                if abs(strike - position.strike) < 0.01:  # Match current strike
                    bid = float(contract.get("bid") or contract.get("bidPrice") or 0)
                    ask = float(contract.get("ask") or contract.get("askPrice") or 0)
                    if bid > 0 and ask > 0:
                        # Cost to buy back = mid price
                        current_close_cost = (bid + ask) / 2
                    break
            except (TypeError, ValueError, AttributeError):
                continue
        
        # If we couldn't find the current contract, estimate based on premium collected
        # Assume we can close at 20% of original premium (conservative estimate)
        if current_close_cost == 0.0 and position.premium_collected > 0:
            premium_per_contract = position.premium_collected / position.contracts
            current_close_cost = premium_per_contract * 0.20
        
        # Find roll candidates: 30-45 DTE, strike >= EMA50
        roll_candidates = []
        target_dte_min = 30
        target_dte_max = 45
        
        for contract in chain:
            try:
                expiry_raw = contract.get("expiry") or contract.get("expirationDate") or contract.get("expDate")
                expiry_date = self._parse_expiry(expiry_raw)
                if expiry_date is None:
                    continue
                
                dte = (expiry_date - today).days
                if dte < target_dte_min or dte > target_dte_max:
                    continue
                
                strike = float(contract.get("strike") or contract.get("strikePrice"))
                if strike < ema50:
                    continue
                
                # Must be a put (delta negative for puts)
                delta = float(contract.get("delta"))
                if delta >= 0:
                    continue
                
                bid = float(contract.get("bid") or contract.get("bidPrice") or 0)
                ask = float(contract.get("ask") or contract.get("askPrice") or 0)
                if bid <= 0 or ask <= 0:
                    continue
                
                # Calculate premium estimate (mid price)
                premium_estimate = (bid + ask) / 2
                
                # Calculate net credit per contract
                net_credit_per_contract = premium_estimate - current_close_cost
                
                # Only suggest if net credit >= 0
                if net_credit_per_contract < 0:
                    continue
                
                # Total net credit for all contracts
                total_net_credit = net_credit_per_contract * position.contracts
                
                roll_candidates.append({
                    "expiry": expiry_date,
                    "strike": strike,
                    "delta": delta,
                    "premium_estimate": premium_estimate,
                    "net_credit_per_contract": net_credit_per_contract,
                    "total_net_credit": total_net_credit,
                    "dte": dte,
                    "oi": int(contract.get("oi") or contract.get("openInterest") or contract.get("open_interest") or 0),
                })
            except (TypeError, ValueError, AttributeError):
                continue
        
        if not roll_candidates:
            return None
        
        # Rank by highest net credit, then highest OI
        roll_candidates.sort(key=lambda c: (-c["total_net_credit"], -c["oi"]))
        best_roll = roll_candidates[0]
        
        # Build reasons
        reasons = []
        reasons.append(f"Roll to {best_roll['dte']} DTE expiry")
        reasons.append(f"New strike ${best_roll['strike']:.2f} >= EMA50 ${ema50:.2f}")
        reasons.append(f"Estimated net credit: ${best_roll['total_net_credit']:.2f}")
        if best_roll["net_credit_per_contract"] > 0:
            reasons.append(f"Premium: ${best_roll['premium_estimate']:.2f} per contract")
        
        return {
            "symbol": position.symbol,
            "current_strike": position.strike,
            "current_expiry": position.expiry,
            "suggested_strike": best_roll["strike"],
            "suggested_expiry": best_roll["expiry"].isoformat(),
            "estimated_net_credit": best_roll["total_net_credit"],
            "reasons": reasons,
        }

    @staticmethod
    def _parse_expiry(value: Any) -> Optional[date]:
        """Best-effort parser to convert an expiry field into a date.
        
        Accepts:
        - date instances (returned as-is)
        - datetime instances (date component only)
        - ISO date strings (YYYY-MM-DD)
        """
        if value is None:
            return None
        
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        
        if isinstance(value, datetime):
            return value.date()
        
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                return None
        
        return None


__all__ = ["RollEngine"]
