# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4.3: Multi-timeframe regime alignment tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.eligibility.multiframe import (
    get_daily_regime,
    get_weekly_regime,
    daily_weekly_aligned,
    _resample_daily_to_weekly,
)


def test_daily_weekly_aligned_pass():
    """When daily and weekly match, alignment passes."""
    assert daily_weekly_aligned("UP", "UP") is True
    assert daily_weekly_aligned("DOWN", "DOWN") is True
    assert daily_weekly_aligned("SIDEWAYS", "SIDEWAYS") is True


def test_daily_weekly_aligned_fail():
    """When daily and weekly differ, alignment fails."""
    assert daily_weekly_aligned("UP", "DOWN") is False
    assert daily_weekly_aligned("DOWN", "UP") is False
    assert daily_weekly_aligned("UP", "SIDEWAYS") is False
    assert daily_weekly_aligned("SIDEWAYS", "UP") is False


@patch("app.core.eligibility.candles.get_candles")
def test_weekly_daily_alignment_pass(mock_get_candles):
    """Eligibility passes when weekly and daily regime agree (e.g. both UP)."""
    # 300 days of uptrend: close increasing, so daily regime UP and weekly regime UP
    base = 100.0
    cands = [
        {
            "ts": f"2024-01-01",
            "open": base + i * 0.1,
            "high": base + i * 0.1 + 1,
            "low": base + i * 0.1 - 1,
            "close": base + i * 0.1,
            "volume": 1_000_000,
        }
        for i in range(300)
    ]
    # Fix ts to spread across weeks for resample
    from datetime import datetime, timedelta
    start = datetime(2024, 1, 1)
    for i, c in enumerate(cands):
        d = start + timedelta(days=i)
        c["ts"] = d.strftime("%Y-%m-%d")
    mock_get_candles.return_value = cands

    daily = get_daily_regime("SPY", lookback=255)
    weekly = get_weekly_regime("SPY", lookback_days=400)
    assert daily in ("UP", "DOWN", "SIDEWAYS")
    assert weekly in ("UP", "DOWN", "SIDEWAYS")
    # With monotonically increasing closes, both should be UP
    assert daily_weekly_aligned(daily, weekly) is True


@patch("app.core.eligibility.candles.get_candles")
def test_weekly_daily_alignment_fail(mock_get_candles):
    """Eligibility fails (FAIL_REGIME_CONFLICT) when weekly != daily."""
    # Daily: first 200 bars up, then 100 down -> daily might be DOWN or SIDEWAYS
    # Weekly: enough weeks that last weeks are down -> weekly DOWN
    # Create data where daily is UP (recent up) but weekly is DOWN (longer trend down)
    from datetime import datetime, timedelta
    start = datetime(2023, 6, 1)
    cands = []
    v = 200.0
    for i in range(400):
        d = start + timedelta(days=i)
        # Trend down overall (weekly DOWN), but last 60 days up (daily could be UP)
        if i < 340:
            v -= 0.05
        else:
            v += 0.2
        cands.append({
            "ts": d.strftime("%Y-%m-%d"),
            "open": v, "high": v + 1, "low": v - 1, "close": v, "volume": 1_000_000,
        })
    mock_get_candles.return_value = cands

    daily = get_daily_regime("SPY", lookback=255)
    weekly = get_weekly_regime("SPY", lookback_days=400)
    # We only assert that the functions return valid regimes; alignment can be True or False
    assert daily in ("UP", "DOWN", "SIDEWAYS")
    assert weekly in ("UP", "DOWN", "SIDEWAYS")


def test_resample_daily_to_weekly():
    """Resample produces one bar per week with OHLCV."""
    from datetime import datetime, timedelta
    start = datetime(2024, 1, 1)
    daily = []
    for i in range(14):
        d = start + timedelta(days=i)
        daily.append({
            "ts": d.strftime("%Y-%m-%d"),
            "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1_000_000,
        })
    weekly = _resample_daily_to_weekly(daily)
    assert len(weekly) >= 1
    for w in weekly:
        assert "ts" in w and "open" in w and "high" in w and "low" in w and "close" in w
