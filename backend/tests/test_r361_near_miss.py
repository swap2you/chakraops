# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R36.1 — deterministic near-miss tests (boundary + safety)."""

from __future__ import annotations

from app.core.decision_engine.explanation import (
    DELTA_NEAR_MISS_EPS,
    DTE_NEAR_MISS_EPS_DAYS,
    RETURN_NEAR_MISS_EPS_PCT,
    compute_near_miss,
)

PROFILE = {
    "name": "balanced",
    "csp_delta_range": [0.20, 0.40],
    "cc_delta_range": [0.20, 0.40],
    "dte_range": [30, 45],
    "min_return_pct": 2.0,
}


def _item(**kw):
    base = {
        "symbol": "AAPL", "strategy": "CSP", "decision_status": "WATCH",
        "reason_codes": [], "risk_flags": [],
        "selected_contract": {"delta": 0.42, "dte": 33},
        "expected_return_pct": 2.5,
    }
    base.update(kw)
    return base


def test_delta_just_inside_epsilon_is_near_miss():
    item = _item(reason_codes=["DELTA_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.40 + DELTA_NEAR_MISS_EPS, "dte": 33})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is True
    assert nm["gate"] == "DELTA_OUT_OF_RANGE"
    assert nm["unit"] == "delta"


def test_delta_just_outside_epsilon_is_not_near_miss():
    item = _item(reason_codes=["DELTA_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.40 + DELTA_NEAR_MISS_EPS + 0.001, "dte": 33})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is False


def test_dte_boundary_near_miss():
    item = _item(reason_codes=["DTE_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.30, "dte": 45 + DTE_NEAR_MISS_EPS_DAYS})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is True
    assert nm["gate"] == "DTE_OUT_OF_RANGE" and nm["unit"] == "days"


def test_dte_beyond_epsilon_not_near_miss():
    item = _item(reason_codes=["DTE_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.30, "dte": 45 + DTE_NEAR_MISS_EPS_DAYS + 1})
    assert compute_near_miss(item, PROFILE)["is_near_miss"] is False


def test_return_near_miss_boundary():
    item = _item(reason_codes=["BELOW_RETURN_THRESHOLD"],
                 expected_return_pct=2.0 - RETURN_NEAR_MISS_EPS_PCT)
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is True
    assert nm["gate"] == "BELOW_RETURN_THRESHOLD" and nm["unit"] == "pct"


def test_blocked_status_is_never_a_near_miss():
    item = _item(decision_status="BLOCKED", reason_codes=["DELTA_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.41, "dte": 33})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is False
    assert nm.get("blocked_by_safety_critical") is True


def test_safety_critical_reason_blocks_near_miss():
    # Even without BLOCKED status, a safety-critical code must prevent near-miss.
    item = _item(reason_codes=["DELTA_OUT_OF_RANGE", "WIDE_SPREAD"],
                 selected_contract={"delta": 0.41, "dte": 33})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is False
    assert nm.get("blocked_by_safety_critical") is True


def test_deterministic_pick_smallest_normalized_distance():
    # Delta misses by 0.005/0.02 = 0.25 norm; DTE misses by 1/3 = 0.33 norm -> delta wins.
    item = _item(reason_codes=["DELTA_OUT_OF_RANGE", "DTE_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.405, "dte": 46})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is True
    assert nm["gate"] == "DELTA_OUT_OF_RANGE"


def test_no_soft_code_means_no_near_miss():
    item = _item(reason_codes=["DELTA_IN_RANGE"], decision_status="ACTIONABLE")
    assert compute_near_miss(item, PROFILE)["is_near_miss"] is False


def test_covered_call_uses_cc_delta_range():
    item = _item(strategy="COVERED_CALL", reason_codes=["DELTA_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.41, "dte": 33})
    nm = compute_near_miss(item, PROFILE)
    assert nm["is_near_miss"] is True


def test_near_miss_is_deterministic_repeatable():
    item = _item(reason_codes=["DELTA_OUT_OF_RANGE"],
                 selected_contract={"delta": 0.415, "dte": 33})
    a = compute_near_miss(item, PROFILE)
    b = compute_near_miss(item, PROFILE)
    assert a == b
