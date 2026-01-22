# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Assignment-Worthy (AW) scoring for CSP candidates.

This module evaluates whether a stock is desirable to own if assigned,
preventing CSP recommendations on stocks that are not assignment-worthy
unless the operator explicitly overrides.
"""

from __future__ import annotations

import logging
from typing import Dict, Literal

logger = logging.getLogger(__name__)

AssignmentLabel = Literal["OK_TO_OWN", "NEUTRAL", "RENT_ONLY"]


def score_assignment_worthiness(
    candidate: Dict[str, any],
    regime: str,
) -> Dict[str, any]:
    """
    Score assignment-worthiness of a CSP candidate.
    
    Uses ONLY existing indicators:
    - EMA50, EMA200
    - Trend alignment
    - Regime (RISK_ON/RISK_OFF)
    - Volatility (ATR)
    - CSP score
    
    Parameters
    ----------
    candidate:
        CSP candidate dictionary with:
        - symbol: str
        - score: int (CSP score 0-100)
        - key_levels: dict with close, ema50, ema200, atr, rsi
        - reasons: list[str]
    regime:
        Market regime: "RISK_ON" or "RISK_OFF"
    
    Returns
    -------
    dict
        Dictionary with:
        - assignment_score: int (0-100)
        - assignment_label: "OK_TO_OWN" | "NEUTRAL" | "RENT_ONLY"
        - assignment_reasons: list[str]
    
    Raises
    ------
    RuntimeError
        If assignment logic fails (should emit HALT alert).
    """
    try:
        symbol = candidate.get("symbol", "")
        key_levels = candidate.get("key_levels", {})
        csp_score = candidate.get("score", 0)
        
        close = key_levels.get("close")
        ema50 = key_levels.get("ema50")
        ema200 = key_levels.get("ema200")
        atr = key_levels.get("atr")
        rsi = key_levels.get("rsi")
        
        # Validate required data
        if close is None or ema50 is None or ema200 is None:
            raise RuntimeError(
                f"Assignment scoring failed for {symbol}: missing required price data"
            )
        
        assignment_score = 0
        assignment_reasons = []
        
        # Factor 1: Strong uptrend (close > EMA200 and EMA50 > EMA200)
        # This indicates a stock you'd want to own
        uptrend_strong = close > ema200 and ema50 > ema200
        if uptrend_strong:
            assignment_score += 40
            assignment_reasons.append("Strong uptrend: close > EMA200 and EMA50 > EMA200")
        elif close > ema200:
            assignment_score += 20
            assignment_reasons.append("Uptrend: close > EMA200 (EMA50 not above EMA200)")
        else:
            # Below EMA200 is concerning for assignment
            assignment_score -= 30
            assignment_reasons.append("Below EMA200: not in strong uptrend")
        
        # Factor 2: Trend alignment (EMA50 slope)
        # Calculate EMA50 slope (trend direction)
        # For simplicity, we use the CSP score as a proxy for trend quality
        # Higher CSP score = better trend alignment
        if csp_score >= 70:
            assignment_score += 30
            assignment_reasons.append(f"Strong trend alignment (CSP score: {csp_score})")
        elif csp_score >= 50:
            assignment_score += 15
            assignment_reasons.append(f"Moderate trend alignment (CSP score: {csp_score})")
        else:
            assignment_score -= 10
            assignment_reasons.append(f"Weak trend alignment (CSP score: {csp_score})")
        
        # Factor 3: Regime alignment
        # RISK_ON regime is better for assignment (you want to own in good markets)
        if regime == "RISK_ON":
            assignment_score += 20
            assignment_reasons.append("RISK_ON regime: favorable for ownership")
        else:
            assignment_score -= 20
            assignment_reasons.append("RISK_OFF regime: less favorable for ownership")
        
        # Factor 4: Volatility (ATR)
        # Lower volatility relative to price = more stable = better to own
        if atr is not None and close > 0:
            atr_pct = (atr / close) * 100
            if atr_pct < 2.0:
                assignment_score += 10
                assignment_reasons.append(f"Low volatility: ATR {atr_pct:.1f}% of price")
            elif atr_pct > 5.0:
                assignment_score -= 15
                assignment_reasons.append(f"High volatility: ATR {atr_pct:.1f}% of price")
        
        # Factor 5: RSI (momentum)
        # Moderate RSI (30-70) is better than extreme
        if rsi is not None:
            if 30 <= rsi <= 70:
                assignment_score += 10
                assignment_reasons.append(f"Moderate RSI: {rsi:.1f} (healthy momentum)")
            elif rsi < 20:
                assignment_score -= 10
                assignment_reasons.append(f"Very oversold RSI: {rsi:.1f} (potential weakness)")
            elif rsi > 80:
                assignment_score -= 5
                assignment_reasons.append(f"Very overbought RSI: {rsi:.1f} (potential reversal)")
        
        # Clamp score to 0-100
        assignment_score = max(0, min(100, assignment_score))
        
        # Determine label based on score
        if assignment_score >= 70:
            assignment_label: AssignmentLabel = "OK_TO_OWN"
        elif assignment_score >= 40:
            assignment_label: AssignmentLabel = "NEUTRAL"
        else:
            assignment_label: AssignmentLabel = "RENT_ONLY"
        
        return {
            "assignment_score": assignment_score,
            "assignment_label": assignment_label,
            "assignment_reasons": assignment_reasons,
        }
    
    except Exception as e:
        # If assignment logic fails, this is a system error
        error_msg = f"Assignment scoring failed for {candidate.get('symbol', 'UNKNOWN')}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


__all__ = ["score_assignment_worthiness", "AssignmentLabel"]
