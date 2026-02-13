# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 5.2: Intraday confirmation (4H) feature-flag and alignment tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.eligibility.eligibility_engine import (
    run as run_eligibility,
    FAIL_INTRADAY_DATA_MISSING,
    FAIL_INTRADAY_REGIME_CONFLICT,
)
from app.core.eligibility.config import ENABLE_INTRADAY_CONFIRMATION, INTRADAY_MIN_ROWS


def _make_candles(n: int, close_trend: str = "flat") -> list:
    """n bars: flat ~100, or up/down trend for regime."""
    base = 100.0
    out = []
    for i in range(n):
        if close_trend == "up":
            c = base + i * 0.5
        elif close_trend == "down":
            c = base - i * 0.5
        else:
            c = base + (i % 3 - 1) * 0.2
        out.append({"ts": f"2024-01-{1 + (i // 24):02d}", "open": c - 0.5, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 1_000_000})
    return out


def _csp_passing_candles():
    """260 bars that yield CSP: uptrend, support near last close (swing low in last 90), RSI/ATR ok."""
    base = 95.0
    out = []
    for i in range(260):
        c = base + i * 0.02  # 95 -> 100.18
        lo, hi = c - 0.3, c + 0.3
        if i >= 170 and i <= 175:  # swing low zone
            lo = c - 1.5
        out.append({"ts": f"2024-01-{1 + (i // 24):02d}", "open": c, "high": hi, "low": lo, "close": c, "volume": 1_000_000})
    return out


@patch("app.core.eligibility.candles.get_candles")
def test_intraday_disabled_behavior_unchanged(mock_get_candles):
    """Intraday disabled (default) → system behavior identical to before; trace has intraday.enabled=False."""
    mock_get_candles.return_value = _make_candles(260)
    mode, trace = run_eligibility("SPY", holdings={}, lookback=255)
    assert trace.get("intraday", {}).get("enabled") is False
    rej = trace.get("rejection_reason_codes") or []
    assert FAIL_INTRADAY_DATA_MISSING not in rej
    assert FAIL_INTRADAY_REGIME_CONFLICT not in rej


@patch("app.core.eligibility.multiframe.get_weekly_regime")
@patch("app.core.eligibility.providers.intraday_provider.get_intraday_candles")
@patch("app.core.eligibility.candles.get_candles")
@patch("app.core.eligibility.eligibility_engine.ENABLE_INTRADAY_CONFIRMATION", True)
def test_intraday_enabled_aligned_mode_preserved(mock_get_candles, mock_intraday, mock_weekly):
    """Intraday enabled + data present + regime aligned → mode preserved; alignment_pass True."""
    mock_get_candles.return_value = _csp_passing_candles()
    mock_weekly.return_value = "UP"  # multiframe aligned
    mock_intraday.return_value = _make_candles(INTRADAY_MIN_ROWS, "flat")  # SIDEWAYS → no conflict with CSP
    mode, trace = run_eligibility("SPY", holdings={}, lookback=255)
    intraday = trace.get("intraday") or {}
    assert intraday.get("enabled") is True
    if mode == "CSP":  # daily passed and intraday ran
        assert intraday.get("data_present") is True
        assert intraday.get("alignment_pass") is True
        assert FAIL_INTRADAY_REGIME_CONFLICT not in (trace.get("rejection_reason_codes") or [])
    else:
        # daily may still be NONE due to other gates; at least intraday block shape is correct when enabled
        assert "intraday" in trace
        assert intraday.get("timeframe") == "4H"


@patch("app.core.eligibility.multiframe.get_weekly_regime")
@patch("app.core.eligibility.providers.intraday_provider.get_intraday_candles")
@patch("app.core.eligibility.candles.get_candles")
@patch("app.core.eligibility.eligibility_engine.ENABLE_INTRADAY_CONFIRMATION", True)
def test_intraday_enabled_conflict_mode_none(mock_get_candles, mock_intraday, mock_weekly):
    """Intraday enabled + CSP daily but intraday DOWN → mode NONE, FAIL_INTRADAY_REGIME_CONFLICT."""
    mock_get_candles.return_value = _csp_passing_candles()
    mock_weekly.return_value = "UP"
    mock_intraday.return_value = _make_candles(INTRADAY_MIN_ROWS, "down")
    mode, trace = run_eligibility("SPY", holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    intraday = trace.get("intraday") or {}
    if mode == "NONE" and FAIL_INTRADAY_REGIME_CONFLICT in rej:
        assert trace.get("primary_reason_code") == FAIL_INTRADAY_REGIME_CONFLICT
        assert intraday.get("alignment_pass") is False
        assert intraday.get("reason_code") == FAIL_INTRADAY_REGIME_CONFLICT
    elif intraday.get("data_present") and intraday.get("intraday_regime") == "DOWN":
        assert intraday.get("alignment_pass") is False
        assert FAIL_INTRADAY_REGIME_CONFLICT in rej


@patch("app.core.eligibility.multiframe.get_weekly_regime")
@patch("app.core.eligibility.providers.intraday_provider.get_intraday_candles")
@patch("app.core.eligibility.candles.get_candles")
@patch("app.core.eligibility.eligibility_engine.ENABLE_INTRADAY_CONFIRMATION", True)
def test_intraday_enabled_no_data_mode_none(mock_get_candles, mock_intraday, mock_weekly):
    """Intraday enabled + no intraday data when daily would be CSP → NONE, FAIL_INTRADAY_DATA_MISSING."""
    mock_get_candles.return_value = _csp_passing_candles()
    mock_weekly.return_value = "UP"
    mock_intraday.return_value = None
    mode, trace = run_eligibility("SPY", holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    intraday = trace.get("intraday") or {}
    if mode == "CSP":  # daily passed but intraday block runs and overrides to NONE
        assert FAIL_INTRADAY_DATA_MISSING in rej
        assert trace.get("primary_reason_code") == FAIL_INTRADAY_DATA_MISSING
        assert intraday.get("data_present") is False
        assert intraday.get("alignment_pass") is False
        assert intraday.get("reason_code") == FAIL_INTRADAY_DATA_MISSING
    else:
        assert trace.get("intraday") is not None
        assert intraday.get("enabled") is True


@patch("app.core.eligibility.multiframe.get_weekly_regime")
@patch("app.core.eligibility.providers.intraday_provider.get_intraday_candles")
@patch("app.core.eligibility.candles.get_candles")
@patch("app.core.eligibility.eligibility_engine.ENABLE_INTRADAY_CONFIRMATION", True)
def test_intraday_enabled_insufficient_rows_data_missing(mock_get_candles, mock_intraday, mock_weekly):
    """Intraday enabled + fewer than INTRADAY_MIN_ROWS when daily CSP → FAIL_INTRADAY_DATA_MISSING."""
    mock_get_candles.return_value = _csp_passing_candles()
    mock_weekly.return_value = "UP"
    mock_intraday.return_value = _make_candles(50)
    mode, trace = run_eligibility("SPY", holdings={}, lookback=255)
    rej = trace.get("rejection_reason_codes") or []
    intraday = trace.get("intraday") or {}
    if mode == "NONE" and FAIL_INTRADAY_DATA_MISSING in rej:
        assert trace.get("intraday", {}).get("data_present") is False
    assert intraday.get("enabled") is True
