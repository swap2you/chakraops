# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.3: Alert severity mapping (informational only). Does not change mode_decision or Stage-2."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.core.scoring.config import SEVERITY_NOW_PCT, SEVERITY_READY_PCT


def compute_alert_severity(
    eligibility_trace: Optional[Dict[str, Any]],
    score_block: Optional[Dict[str, Any]],
    tier: Optional[str],
    spot: Optional[float],
) -> Dict[str, Any]:
    """
    Classify candidate into operational readiness: INFO | READY | NOW | INVALID.
    Deterministic; no stochastic logic. Missing data → INFO.
    """
    el = eligibility_trace or {}
    mode = (el.get("mode_decision") or "NONE").strip().upper()

    # Case A — mode_decision == NONE → INVALID
    if mode == "NONE":
        return {
            "severity": "INVALID",
            "reason": el.get("primary_reason_code") or "NONE",
            "distance_metric_used": None,
            "threshold_used": None,
            "near_level_type": None,
        }

    # Case B — CSP or CC
    tier_str = (tier or "NONE").strip().upper()

    # Determine relevant level and distance
    if mode == "CSP":
        distance_pct = el.get("distance_to_support_pct")
        near_level_type = "SUPPORT"
        near_pass = _get_near_pass(el, "NEAR_SUPPORT")
    else:
        distance_pct = el.get("distance_to_resistance_pct")
        near_level_type = "RESISTANCE"
        near_pass = _get_near_pass(el, "NEAR_RESISTANCE")

    # Missing distance or near_*_pass is False → INFO
    if distance_pct is None:
        return {
            "severity": "INFO",
            "reason": "distance_missing",
            "distance_metric_used": None,
            "threshold_used": None,
            "near_level_type": near_level_type if mode in ("CSP", "CC") else None,
        }
    try:
        distance_val = float(distance_pct)
    except (TypeError, ValueError):
        return {
            "severity": "INFO",
            "reason": "distance_invalid",
            "distance_metric_used": None,
            "threshold_used": None,
            "near_level_type": near_level_type,
        }

    if near_pass is False:
        return {
            "severity": "INFO",
            "reason": "near_level_fail",
            "distance_metric_used": distance_val,
            "threshold_used": SEVERITY_READY_PCT,
            "near_level_type": near_level_type,
        }

    # Tier A and distance <= NOW → NOW (Tier C cannot become NOW)
    if tier_str == "A" and distance_val <= SEVERITY_NOW_PCT:
        return {
            "severity": "NOW",
            "reason": "tier_a_near_level",
            "distance_metric_used": distance_val,
            "threshold_used": SEVERITY_NOW_PCT,
            "near_level_type": near_level_type,
        }

    # Tier A or B and distance <= READY → READY
    if tier_str in ("A", "B") and distance_val <= SEVERITY_READY_PCT:
        return {
            "severity": "READY",
            "reason": "tier_ready_near_level",
            "distance_metric_used": distance_val,
            "threshold_used": SEVERITY_READY_PCT,
            "near_level_type": near_level_type,
        }

    return {
        "severity": "INFO",
        "reason": "beyond_threshold",
        "distance_metric_used": distance_val,
        "threshold_used": SEVERITY_READY_PCT,
        "near_level_type": near_level_type,
    }


def _get_near_pass(el: Dict[str, Any], rule_name: str) -> Optional[bool]:
    """Get passed flag for NEAR_SUPPORT or NEAR_RESISTANCE from rule_checks."""
    for rc in el.get("rule_checks") or []:
        if (rc.get("name") or "").strip() == rule_name:
            return rc.get("passed")
    return None
