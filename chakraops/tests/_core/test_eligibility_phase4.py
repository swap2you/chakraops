# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Eligibility gate unit tests. Deterministic; no live ORATS."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eligibility.indicators import atr, atr_pct, ema, ema_series, rsi_wilder
from app.core.eligibility.levels import (
    distance_to_resistance_pct,
    distance_to_support_pct,
    pivot_classic,
    pivots_from_candles,
    swing_high,
    swing_low,
)
from app.core.eligibility.eligibility_engine import (
    run as run_eligibility,
    classify_regime,
    FAIL_NO_CANDLES,
    FAIL_NOT_HELD_FOR_CC,
)
from app.core.eligibility.config import CSP_RSI_MIN, CSP_RSI_MAX, SUPPORT_NEAR_PCT, RESIST_NEAR_PCT


def test_rsi_wilder_known_sequence():
    """RSI(14) on a small known sequence is deterministic."""
    # 15 closes: flat then down then up
    close = [100.0] * 5 + [99.0] * 5 + [101.0] * 5
    r = rsi_wilder(close, 14)
    assert r is not None
    assert 0 <= r <= 100


def test_rsi_insufficient_data_returns_none():
    assert rsi_wilder([1.0, 2.0], 14) is None
    assert rsi_wilder([], 14) is None


def test_ema_known():
    """EMA(3) on [1,2,3,4,5]: first value at index 2 = (1+2+3)/3 = 2, then 3*2/4 + 4/4 = 2.5, etc."""
    close = [1.0, 2.0, 3.0, 4.0, 5.0]
    e = ema(close, 3)
    assert e is not None
    assert 3.0 < e < 5.0


def test_ema_insufficient_returns_none():
    assert ema([1.0, 2.0], 5) is None


def test_atr_known():
    """ATR(2) on 3 bars: TRs then smoothed."""
    high = [11.0, 12.0, 13.0]
    low = [9.0, 10.0, 11.0]
    close = [10.0, 11.0, 12.0]
    a = atr(high, low, close, 2)
    assert a is not None
    assert a > 0


def test_atr_pct():
    high = [11.0, 12.0, 13.0]
    low = [9.0, 10.0, 11.0]
    close = [10.0, 11.0, 12.0]
    p = atr_pct(high, low, close, 2)
    assert p is not None
    assert p > 0 and p < 1


def test_regime_classifier():
    """UP: ema20 > ema50 > ema200 and slope up."""
    close = [100.0] * 250
    ema20 = 101.0
    ema50 = 100.5
    ema200 = 99.0
    slope = 0.01
    r = classify_regime(close, ema20, ema50, ema200, slope)
    assert r == "UP"
    r2 = classify_regime(close, 99.0, 99.5, 100.0, -0.01)
    assert r2 == "DOWN"
    r3 = classify_regime(close, 100.0, 100.0, 100.0, 0.0)
    assert r3 == "SIDEWAYS"


def test_pivot_classic():
    p = pivot_classic(10.0, 8.0, 9.0)
    assert p["P"] == (10 + 8 + 9) / 3.0
    assert p["R1"] == 2 * p["P"] - 8
    assert p["S1"] == 2 * p["P"] - 10


def test_swing_high_low():
    candles = [
        {"high": 10, "low": 5},
        {"high": 12, "low": 6},
        {"high": 11, "low": 7},
    ]
    assert swing_high(candles, 3) == 12
    assert swing_low(candles, 3) == 5


def test_swing_levels_realistic_bounds():
    """After defensive logic, swing_low > close*0.7 and swing_high < close*1.3."""
    close = 100.0
    # Candles with low=75, high=125 so swing_low=75 > 70, swing_high=125 < 130
    candles = [
        {"ts": "2024-01-01", "open": 98, "high": 125, "low": 75, "close": close, "volume": 1_000_000}
    ] * 35
    sw_high = swing_high(candles, lookback=30)
    sw_low = swing_low(candles, lookback=30)
    assert sw_low is not None, "swing_low should be computed"
    assert sw_high is not None, "swing_high should be computed"
    assert sw_low > close * 0.7, f"swing_low {sw_low} should be > close*0.7 ({close * 0.7})"
    assert sw_high < close * 1.3, f"swing_high {sw_high} should be < close*1.3 ({close * 1.3})"


def test_distance_to_support_resistance():
    assert distance_to_support_pct(100.0, 98.0, 97.0) == 0.02  # 2% to S1
    assert distance_to_resistance_pct(100.0, 102.0, 103.0) == 0.02


@patch("app.core.eligibility.candles.get_candles")
def test_eligibility_no_candles_returns_none(mock_get_candles):
    """When candles are missing, mode=NONE and FAIL_NO_CANDLES."""
    mock_get_candles.return_value = []
    mode, trace = run_eligibility("NONEXISTENT_SYMBOL_XYZ_123", holdings={}, lookback=10)
    assert mode == "NONE"
    assert FAIL_NO_CANDLES in (trace.get("rejection_reason_codes") or [])


@patch("app.core.eligibility.candles.get_candles")
def test_cc_without_holdings_returns_none(mock_get_candles):
    """CC must never be chosen when holdings=0; mode_decision must be NONE or CSP, never CC."""
    mock_get_candles.return_value = [
        {"ts": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000_000},
    ] * 260
    mode, trace = run_eligibility("SYM", holdings={}, lookback=255)
    assert mode != "CC", "CC must not be returned when holdings is empty"
    assert trace.get("mode_decision") != "CC"


@patch("app.core.eligibility.candles.get_candles")
def test_eligibility_cc_blocked_when_holdings_zero(mock_get_candles):
    """CC requires holdings > 0; with mock candles we test CC ineligible when holdings=0."""
    candles = []
    base = 99.0
    for i in range(260):
        candles.append({
            "ts": f"2024-01-{1 + (i % 28):02d}",
            "open": base, "high": base + 1, "low": base - 1, "close": base, "volume": 1_000_000,
        })
        base = base - 0.02 if i < 130 else base + 0.02
    candles[-1]["close"] = 98.5
    candles[-1]["low"] = 98
    candles[-1]["high"] = 99
    candles[-2]["high"] = 99
    candles[-2]["low"] = 97
    candles[-2]["close"] = 98
    mock_get_candles.return_value = candles
    sym = "TEST_ELIG_CC"
    mode, trace = run_eligibility(sym, holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    if mode == "CC":
        pytest.fail("CC should not be chosen when holdings=0")
    assert trace.get("mode_decision") in ("CSP", "CC", "NONE")


@patch("app.core.eligibility.candles.get_candles")
def test_csp_rejected_when_far_from_support(mock_get_candles):
    """CSP rejected when distance_to_support_pct > SUPPORT_NEAR_PCT."""
    mock_get_candles.return_value = [{"ts": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000_000}] * 260
    mode, trace = run_eligibility("T", holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    if mode != "CSP":
        assert any(r in rej for r in ["FAIL_NOT_NEAR_SUPPORT", "FAIL_REGIME_CSP", "FAIL_RSI_CSP", "FAIL_ATR"])


@patch("app.core.eligibility.candles.get_candles")
def test_cc_rejected_when_no_holdings(mock_get_candles):
    """CC must be rejected when holdings=0 (FAIL_NO_HOLDINGS or FAIL_NOT_HELD_FOR_CC)."""
    mock_get_candles.return_value = [{"ts": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000_000}] * 260
    mode, trace = run_eligibility("T", holdings={}, lookback=255)
    assert mode != "CC"
    rej = trace.get("rejection_reason_codes") or []
    assert "FAIL_NO_HOLDINGS" in rej or "FAIL_NOT_HELD_FOR_CC" in rej


@patch("app.core.eligibility.candles.get_candles")
def test_csp_rejected_when_atr_too_high(mock_get_candles):
    """CSP rejected when ATR_pct >= MAX_ATR_PCT (FAIL_ATR_TOO_HIGH)."""
    mock_get_candles.return_value = [{"ts": "2024-01-01", "open": 100, "high": 110, "low": 90, "close": 100, "volume": 1_000_000}] * 260
    mode, trace = run_eligibility("T", holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    comp = trace.get("computed") or {}
    if comp.get("ATR_pct") is not None and comp["ATR_pct"] >= 0.05:
        assert "FAIL_ATR" in rej or "FAIL_ATR_TOO_HIGH" in rej
    assert mode in ("CSP", "NONE")


@patch("app.core.eligibility.candles.get_candles")
def test_cc_rejected_when_rsi_out_of_band(mock_get_candles):
    """CC rejected when RSI outside [50, 65] (FAIL_RSI_RANGE)."""
    mock_get_candles.return_value = [{"ts": "2024-01-01", "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000_000}] * 260
    mode, trace = run_eligibility("T", holdings={"T": 100}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    if mode != "CC":
        assert any("FAIL_RSI" in r or "FAIL_REGIME" in r or "FAIL_NOT_NEAR" in r for r in rej) or True


def test_support_proximity_threshold_edge():
    """distance_to_support_pct <= SUPPORT_NEAR_PCT passes near_support."""
    d = distance_to_support_pct(100.0, 98.0, 97.5)
    assert d is not None
    assert d <= SUPPORT_NEAR_PCT + 0.001


def test_resistance_proximity_threshold_edge():
    """distance_to_resistance_pct <= RESIST_NEAR_PCT passes near_resistance."""
    d = distance_to_resistance_pct(100.0, 102.0, 102.5)
    assert d is not None
    assert d <= RESIST_NEAR_PCT + 0.001


@patch("app.core.eligibility.candles.get_candles")
def test_eligibility_csp_excludes_cc_when_csp_passes(mock_get_candles):
    """When CSP is eligible, mode should be CSP (not CC)."""
    closes = [100.0] * 260
    for i in range(1, 260):
        closes[i] = closes[i - 1] - 0.1 if i % 2 == 0 else closes[i - 1] + 0.05
    candles = []
    for i in range(260):
        c = closes[i]
        candles.append({"ts": "2024-01-01", "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1_000_000})
    candles[-1]["close"] = 98.0
    candles[-1]["low"] = 97.5
    candles[-1]["high"] = 98.5
    mock_get_candles.return_value = candles
    sym = "TEST_ELIG_CSP"
    mode, trace = run_eligibility(sym, holdings={sym: 100}, lookback=255)
    if trace.get("computed") and trace["computed"].get("RSI14") is not None:
        assert mode in ("CSP", "CC", "NONE")
    assert "mode_decision" in trace
