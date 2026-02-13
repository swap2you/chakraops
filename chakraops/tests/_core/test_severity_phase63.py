# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.3: Alert severity mapping (informational only). No decision impact."""

from __future__ import annotations

import pytest

from app.core.scoring.severity import compute_alert_severity
from app.core.scoring.config import SEVERITY_NOW_PCT, SEVERITY_READY_PCT


def test_none_mode_invalid():
    """mode NONE -> severity INVALID, reason = primary_reason_code."""
    el = {"mode_decision": "NONE", "primary_reason_code": "FAIL_RSI_CSP"}
    out = compute_alert_severity(el, {}, "NONE", 100.0)
    assert out["severity"] == "INVALID"
    assert out["reason"] == "FAIL_RSI_CSP"
    assert out["distance_metric_used"] is None
    assert out["threshold_used"] is None
    assert out["near_level_type"] is None


def test_tier_a_within_now_now():
    """Tier A and distance <= NOW threshold -> NOW."""
    el = {
        "mode_decision": "CSP",
        "distance_to_support_pct": 0.005,
        "rule_checks": [{"name": "NEAR_SUPPORT", "passed": True}],
    }
    out = compute_alert_severity(el, {}, "A", 100.0)
    assert out["severity"] == "NOW"
    assert out["distance_metric_used"] == 0.005
    assert out["threshold_used"] == SEVERITY_NOW_PCT
    assert out["near_level_type"] == "SUPPORT"


def test_tier_a_within_ready_not_now_readiness():
    """Tier A within READY but not NOW -> READY."""
    el = {
        "mode_decision": "CSP",
        "distance_to_support_pct": 0.01,
        "rule_checks": [{"name": "NEAR_SUPPORT", "passed": True}],
    }
    out = compute_alert_severity(el, {}, "A", 100.0)
    assert out["severity"] == "READY"
    assert out["distance_metric_used"] == 0.01
    assert out["threshold_used"] == SEVERITY_READY_PCT


def test_tier_b_within_ready_readiness():
    """Tier B within READY -> READY."""
    el = {
        "mode_decision": "CC",
        "distance_to_resistance_pct": 0.012,
        "rule_checks": [{"name": "NEAR_RESISTANCE", "passed": True}],
    }
    out = compute_alert_severity(el, {}, "B", 100.0)
    assert out["severity"] == "READY"
    assert out["near_level_type"] == "RESISTANCE"


def test_tier_c_within_now_still_info():
    """Tier C within NOW threshold -> still INFO (Tier C cannot become NOW)."""
    el = {
        "mode_decision": "CSP",
        "distance_to_support_pct": 0.005,
        "rule_checks": [{"name": "NEAR_SUPPORT", "passed": True}],
    }
    out = compute_alert_severity(el, {}, "C", 100.0)
    assert out["severity"] == "INFO"
    assert out["reason"] == "beyond_threshold"


def test_distance_missing_info():
    """Distance missing -> INFO."""
    el = {"mode_decision": "CSP", "rule_checks": [{"name": "NEAR_SUPPORT", "passed": True}]}
    out = compute_alert_severity(el, {}, "A", 100.0)
    assert out["severity"] == "INFO"
    assert out["reason"] == "distance_missing"
    assert out["distance_metric_used"] is None


def test_near_level_fail_downgrade_info():
    """If near_support_pass / near_resistance_pass is False -> INFO."""
    el = {
        "mode_decision": "CSP",
        "distance_to_support_pct": 0.005,
        "rule_checks": [{"name": "NEAR_SUPPORT", "passed": False}],
    }
    out = compute_alert_severity(el, {}, "A", 100.0)
    assert out["severity"] == "INFO"
    assert out["reason"] == "near_level_fail"


def test_no_impact_to_mode_decision():
    """Regression: eligibility_trace and mode_decision unchanged when severity added."""
    el = {"mode_decision": "CSP", "distance_to_support_pct": 0.01, "rule_checks": [{"name": "NEAR_SUPPORT", "passed": True}]}
    score_block = {"composite_score": 75}
    out = compute_alert_severity(el, score_block, "B", 100.0)
    assert el["mode_decision"] == "CSP"
    assert out["severity"] in ("INFO", "READY", "NOW", "INVALID")
