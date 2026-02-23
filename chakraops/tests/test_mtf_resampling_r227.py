# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R22.7 Fix Pack: MTF resampling — weekly/monthly from daily OHLC; no copying daily into W/M."""

from __future__ import annotations


def _synthetic_daily_candles(n_days: int = 60) -> list[dict]:
    """Synthetic daily OHLCV: 60 days with varying high/low so weekly bars differ from daily."""
    from datetime import datetime, timedelta
    base = datetime(2025, 1, 1)
    out = []
    for i in range(n_days):
        d = (i % 7) * 1.0 + (i // 7) * 0.5
        dt = base + timedelta(days=i)
        out.append({
            "ts": dt.strftime("%Y-%m-%d"),
            "open": 100.0 + i * 0.2,
            "high": 100.5 + i * 0.2 + d,
            "low": 99.5 + i * 0.2 - d,
            "close": 100.0 + (i + 1) * 0.2,
            "volume": 1_000_000 + i * 1000,
        })
    return out


def test_weekly_resampling_differs_from_daily_bar_count() -> None:
    """Given synthetic daily data, weekly bar count < daily bar count; weekly bars are distinct."""
    from app.core.eligibility.multiframe import _resample_daily_to_weekly, _resample_daily_to_monthly

    daily = _synthetic_daily_candles(60)
    weekly = _resample_daily_to_weekly(daily)
    monthly = _resample_daily_to_monthly(daily)
    assert len(daily) == 60
    assert len(weekly) < len(daily), "Weekly bar count must be less than daily"
    assert len(monthly) < len(weekly), "Monthly bar count must be less than weekly"
    assert len(weekly) >= 8, "60 days -> at least 8 weeks"
    assert len(monthly) >= 2, "60 days -> at least 2 months"
    for w in weekly:
        assert "high" in w and "low" in w and "open" in w and "close" in w and "volume" in w
        assert w["high"] >= w["low"]
        assert w["volume"] >= 0


def test_mtf_sr_uses_weekly_series_length() -> None:
    """S/R computed on weekly series uses weekly bar count (not daily)."""
    from app.core.eligibility.multiframe import _resample_daily_to_weekly
    from app.core.eligibility.swing_cluster import compute_support_resistance

    daily = _synthetic_daily_candles(90)
    weekly = _resample_daily_to_weekly(daily)
    spot = 105.0
    atr14 = 1.5
    window_w = min(20, len(weekly))
    sr = compute_support_resistance(weekly, spot, atr14, window_w, 3, 0.5, 0.006)
    assert "support_level" in sr or "resistance_level" in sr or sr.get("cluster_count") is not None
    assert len(weekly) < len(daily)
    assert sr.get("method") == "swing_cluster"
