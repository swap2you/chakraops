# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
Verdict resolution with strict precedence.

This module ensures consistent verdict determination across all evaluation paths.
All views (Universe, Ticker, Dashboard) must use these functions for verdicts.

Precedence order (highest to lowest):
1. BLOCKED (position/exposure blocking)
2. DATA_INCOMPLETE_FATAL (missing required EOD fields: price, options chain)
3. HOLD (regime/risk gating, exposure limits)
4. ELIGIBLE

DATA_INCOMPLETE classification:
- DATA_INCOMPLETE_FATAL: Missing price or no options chain at all
- DATA_INCOMPLETE_INTRADAY: Missing bid/ask/volume (NON-FATAL when market CLOSED)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DataIncompleteType(str, Enum):
    """Classification of DATA_INCOMPLETE severity."""
    FATAL = "DATA_INCOMPLETE_FATAL"  # Missing price or chain - blocks trade
    INTRADAY = "DATA_INCOMPLETE_INTRADAY"  # Missing bid/ask/volume - non-fatal when CLOSED
    NONE = "NONE"  # No data incompleteness


class MarketStatus(str, Enum):
    """Market trading status."""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


# Fields that are FATAL if missing (required for EOD options strategy)
FATAL_MISSING_FIELDS = frozenset({"price"})

# Fields that are only relevant during market hours or optional for display (non-fatal when missing)
# ORATS /live/summaries may not include bid/ask/volume/avg_volume/iv_rank; do not FATAL when only these are missing
INTRADAY_ONLY_FIELDS = frozenset({
    "bid", "ask", "volume", "bidSize", "askSize",
    "avg_volume", "iv_rank",  # optional for UI/scoring; ORATS summaries may omit
})


@dataclass
class VerdictResolution:
    """Result of verdict resolution."""
    verdict: str  # ELIGIBLE, HOLD, BLOCKED
    reason: str
    reason_code: str  # e.g. POSITION_BLOCKED, DATA_INCOMPLETE_FATAL, REGIME_RISK_OFF
    data_incomplete_type: DataIncompleteType = DataIncompleteType.NONE
    was_downgraded: bool = False  # True if verdict was changed from original
    downgrade_reason: Optional[str] = None


def classify_data_incompleteness(
    missing_fields: List[str],
    market_status: MarketStatus,
    has_options_chain: bool = True,
) -> Tuple[DataIncompleteType, str]:
    """
    Classify DATA_INCOMPLETE severity based on missing fields and market status.
    
    Args:
        missing_fields: List of missing field names
        market_status: Current market status (OPEN/CLOSED)
        has_options_chain: Whether options chain data exists at all
    
    Returns:
        Tuple of (DataIncompleteType, reason string)
    """
    if not missing_fields and has_options_chain:
        return DataIncompleteType.NONE, ""
    
    # No options chain at all is FATAL
    if not has_options_chain:
        return DataIncompleteType.FATAL, "DATA_INCOMPLETE_FATAL: no options chain available"
    
    missing_set = set(f.lower() for f in missing_fields)
    
    # Check for FATAL missing fields
    fatal_missing = missing_set & {f.lower() for f in FATAL_MISSING_FIELDS}
    if fatal_missing:
        return (
            DataIncompleteType.FATAL,
            f"DATA_INCOMPLETE_FATAL: missing required fields ({', '.join(sorted(fatal_missing))})"
        )
    
    # Check for intraday-only missing fields
    intraday_missing = missing_set & {f.lower() for f in INTRADAY_ONLY_FIELDS}
    other_missing = missing_set - intraday_missing
    
    # If there are non-intraday missing fields, it's FATAL
    if other_missing:
        return (
            DataIncompleteType.FATAL,
            f"DATA_INCOMPLETE_FATAL: missing fields ({', '.join(sorted(other_missing))})"
        )
    
    # Only intraday fields missing
    if intraday_missing:
        if market_status == MarketStatus.CLOSED:
            # Non-fatal when market is closed - bid/ask/volume not expected
            return (
                DataIncompleteType.INTRADAY,
                f"DATA_INCOMPLETE_INTRADAY: missing {', '.join(sorted(intraday_missing))} (non-fatal, market CLOSED)"
            )
        else:
            # During market hours, missing bid/ask/volume is more concerning but not fatal
            return (
                DataIncompleteType.INTRADAY,
                f"DATA_INCOMPLETE_INTRADAY: missing {', '.join(sorted(intraday_missing))}"
            )
    
    return DataIncompleteType.NONE, ""


def resolve_final_verdict(
    *,
    # Current evaluation state
    current_verdict: str,
    current_reason: str,
    score: int,
    # Position/exposure blocking
    position_blocked: bool = False,
    position_reason: Optional[str] = None,
    exposure_blocked: bool = False,
    exposure_reason: Optional[str] = None,
    # Data completeness
    missing_fields: Optional[List[str]] = None,
    has_options_chain: bool = True,
    data_completeness: float = 1.0,
    # Market context
    market_status: MarketStatus = MarketStatus.UNKNOWN,
    market_regime: Optional[str] = None,  # RISK_ON, NEUTRAL, RISK_OFF
) -> VerdictResolution:
    """
    Resolve final verdict with strict precedence.
    
    This is THE SINGLE FUNCTION that determines verdicts. All views must use this.
    
    Precedence order:
    1. BLOCKED (position/exposure blocking)
    2. DATA_INCOMPLETE_FATAL (missing required EOD fields)
    3. HOLD (regime/risk gating)
    4. ELIGIBLE
    
    Args:
        current_verdict: Current verdict from evaluation
        current_reason: Current reason string
        score: Current score (0-100)
        position_blocked: Whether position blocks this trade
        position_reason: Reason for position blocking
        exposure_blocked: Whether exposure limits are exceeded
        exposure_reason: Reason for exposure blocking
        missing_fields: List of missing field names
        has_options_chain: Whether options chain exists
        data_completeness: Data completeness ratio (0-1)
        market_status: Current market status
        market_regime: Market regime (RISK_ON/NEUTRAL/RISK_OFF)
    
    Returns:
        VerdictResolution with final verdict and reason
    """
    resolution = VerdictResolution(
        verdict=current_verdict,
        reason=current_reason,
        reason_code="ORIGINAL",
    )
    
    # 1. BLOCKED: Position/exposure blocking (highest priority)
    if position_blocked:
        resolution.verdict = "BLOCKED"
        resolution.reason = position_reason or "POSITION_ALREADY_OPEN"
        resolution.reason_code = "POSITION_BLOCKED"
        if current_verdict != "BLOCKED":
            resolution.was_downgraded = True
            resolution.downgrade_reason = "Position blocking"
        return resolution
    
    if exposure_blocked:
        resolution.verdict = "BLOCKED"
        resolution.reason = exposure_reason or "EXPOSURE_CAP_REACHED"
        resolution.reason_code = "EXPOSURE_BLOCKED"
        if current_verdict != "BLOCKED":
            resolution.was_downgraded = True
            resolution.downgrade_reason = "Exposure limits exceeded"
        return resolution
    
    # 2. DATA_INCOMPLETE_FATAL: Missing required EOD fields
    missing = missing_fields or []
    data_type, data_reason = classify_data_incompleteness(
        missing, market_status, has_options_chain
    )
    resolution.data_incomplete_type = data_type
    
    if data_type == DataIncompleteType.FATAL:
        resolution.verdict = "HOLD"
        resolution.reason = data_reason
        resolution.reason_code = "DATA_INCOMPLETE_FATAL"
        if current_verdict == "ELIGIBLE":
            resolution.was_downgraded = True
            resolution.downgrade_reason = "Fatal data incompleteness"
        return resolution
    
    # 3. HOLD: Regime/risk gating
    if market_regime == "RISK_OFF":
        resolution.verdict = "HOLD"
        resolution.reason = "Blocked by market regime: RISK_OFF"
        resolution.reason_code = "REGIME_RISK_OFF"
        if current_verdict == "ELIGIBLE":
            resolution.was_downgraded = True
            resolution.downgrade_reason = "Market regime RISK_OFF"
        return resolution
    
    # 4. If we reach here with ELIGIBLE, it stays ELIGIBLE
    # DATA_INCOMPLETE_INTRADAY does NOT block when market is CLOSED
    if current_verdict == "ELIGIBLE":
        resolution.verdict = "ELIGIBLE"
        resolution.reason_code = "ELIGIBLE"
        # Add note about intraday data if applicable
        if data_type == DataIncompleteType.INTRADAY and market_status == MarketStatus.CLOSED:
            if not resolution.reason.endswith(")"):
                resolution.reason = f"{resolution.reason} (bid/ask N/A: market closed)"
        return resolution
    
    # 5. Preserve current verdict (HOLD or BLOCKED from evaluation)
    return resolution


def apply_verdict_to_result(
    result: Dict[str, Any],
    market_status: MarketStatus,
) -> Dict[str, Any]:
    """
    Apply verdict resolution to an evaluation result dict.
    
    Mutates and returns the result dict with corrected verdict.
    """
    resolution = resolve_final_verdict(
        current_verdict=result.get("verdict", "UNKNOWN"),
        current_reason=result.get("primary_reason", ""),
        score=result.get("score", 0),
        position_blocked=result.get("position_open", False) and result.get("position_reason"),
        position_reason=result.get("position_reason"),
        exposure_blocked=False,  # Already handled in evaluation
        missing_fields=result.get("missing_fields", []),
        has_options_chain=result.get("options_available", True),
        data_completeness=result.get("data_completeness", 1.0),
        market_status=market_status,
        market_regime=result.get("regime"),
    )
    
    result["verdict"] = resolution.verdict
    result["final_verdict"] = resolution.verdict
    result["primary_reason"] = resolution.reason
    result["verdict_reason_code"] = resolution.reason_code
    result["data_incomplete_type"] = resolution.data_incomplete_type.value
    
    if resolution.was_downgraded:
        result["verdict_downgraded"] = True
        result["verdict_downgrade_reason"] = resolution.downgrade_reason
    
    return result


__all__ = [
    "DataIncompleteType",
    "MarketStatus",
    "VerdictResolution",
    "classify_data_incompleteness",
    "resolve_final_verdict",
    "apply_verdict_to_result",
    "FATAL_MISSING_FIELDS",
    "INTRADAY_ONLY_FIELDS",
]
