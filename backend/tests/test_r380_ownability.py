# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — ownability gate tests."""

from app.core.decision_engine.wheel_v2.ownability import evaluate_ownability


def test_ownability_fail_closed_missing_critical():
    r = evaluate_ownability({"symbol": "AAA"})
    assert r.ownable is False
    assert "OWNABILITY_MISSING_CRITICAL" in r.reason_codes
    assert "market_regime" in r.missing_critical
    assert "stage1_status" in r.missing_critical
    assert "price" in r.missing_critical


def test_ownability_pass_bull_quality():
    r = evaluate_ownability(
        {"market_regime": "BULL", "price": 100.0, "earnings_days": 40},
        stage1_status="PASS",
    )
    assert r.ownable is True
    assert "OWNABLE" in r.reason_codes
    assert r.missing_critical == []


def test_ownability_blocks_bear_regime():
    r = evaluate_ownability(
        {"market_regime": "BEAR", "price": 50.0, "earnings_days": 30},
        stage1_status="PASS",
    )
    assert r.ownable is False
    assert "REGIME_NOT_OWNABLE" in r.reason_codes


def test_ownability_earnings_blackout():
    r = evaluate_ownability(
        {"market_regime": "BULL", "price": 100.0, "earnings_days": 2},
        stage1_status="PASS",
        earnings_blackout_days=7,
    )
    assert r.ownable is False
    assert "EARNINGS_BLACKOUT" in r.reason_codes


def test_ownability_quality_fail():
    r = evaluate_ownability(
        {"market_regime": "NEUTRAL", "price": 80.0, "earnings_days": 20},
        stage1_status="FAIL",
    )
    assert r.ownable is False
    assert "QUALITY_NOT_PASS" in r.reason_codes
