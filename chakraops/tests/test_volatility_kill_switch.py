# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for volatility kill switch (Phase 2.2)."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.core.risk.volatility_kill_switch import (
    fetch_vix,
    compute_spy_range,
    is_volatility_high,
)


class TestFetchVix:
    """Tests for fetch_vix."""

    def test_fetch_vix_returns_float_when_data_available(self) -> None:
        """When yfinance returns VIX data, fetch_vix returns latest close."""
        import pandas as pd
        df = pd.DataFrame({"Close": [17.0, 18.0, 18.5]})
        with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_yf.Ticker.return_value = mock_ticker
            result = fetch_vix(lookback_days=5)
            assert result is not None
            assert result == 18.5

    def test_fetch_vix_returns_none_when_empty(self) -> None:
        """When yfinance returns empty, fetch_vix returns None."""
        import pandas as pd
        with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = pd.DataFrame()
            mock_yf.Ticker.return_value = mock_ticker
            result = fetch_vix(lookback_days=5)
            assert result is None

    def test_fetch_vix_returns_none_when_yf_unavailable(self) -> None:
        """When yf is None (yfinance not installed), fetch_vix returns None."""
        with patch("app.core.risk.volatility_kill_switch.yf", None):
            result = fetch_vix(lookback_days=5)
            assert result is None


class TestComputeSpyRange:
    """Tests for compute_spy_range."""

    def test_compute_spy_range_returns_tuple_when_sufficient_data(self) -> None:
        """When SPY has 21+ rows, returns (day_range, atr_20)."""
        import pandas as pd
        import numpy as np
        n = 25
        dates = pd.date_range(start="2025-01-01", periods=n, freq="B")
        np.random.seed(42)
        close = 400 + np.cumsum(np.random.randn(n) * 2)
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        df = pd.DataFrame({
            "Date": dates,
            "Open": close - 0.5,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.random.randint(50_000_000, 100_000_000, n),
        }).set_index("Date")

        with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_yf.Ticker.return_value = mock_ticker

            day_range, atr_20 = compute_spy_range(lookback_days=25)
            assert day_range is not None
            assert atr_20 is not None
            assert atr_20 > 0

    def test_compute_spy_range_returns_none_when_insufficient_data(self) -> None:
        """When SPY has fewer than 21 rows, atr_20 is None."""
        import pandas as pd
        n = 10
        dates = pd.date_range(start="2025-01-01", periods=n, freq="B")
        df = pd.DataFrame({
            "Date": dates,
            "Open": [400.0] * n,
            "High": [401.0] * n,
            "Low": [399.0] * n,
            "Close": [400.0] * n,
            "Volume": [80_000_000] * n,
        }).set_index("Date")

        with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_yf.Ticker.return_value = mock_ticker

            day_range, atr_20 = compute_spy_range(lookback_days=25)
            assert atr_20 is None


class TestIsVolatilityHigh:
    """Tests for is_volatility_high with mocked VIX and SPY."""

    def test_returns_true_when_vix_above_threshold(self) -> None:
        """When VIX close > vix_threshold, returns True."""
        config = {"vix_threshold": 20.0, "vix_change_pct": 20.0, "range_multiplier": 2.0}
        with patch("app.core.risk.volatility_kill_switch.fetch_vix", return_value=25.0):
            with patch("app.core.risk.volatility_kill_switch.compute_spy_range", return_value=(1.0, 2.0)):
                with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
                    mock_ticker = MagicMock()
                    import pandas as pd
                    mock_ticker.history.return_value = pd.DataFrame({"Close": [20.0, 21.0, 22.0, 23.0]})
                    mock_yf.Ticker.return_value = mock_ticker
                    assert is_volatility_high(config) is True

    def test_returns_false_when_vix_below_threshold(self) -> None:
        """When VIX close <= threshold and no other trigger, returns False."""
        import pandas as pd
        config = {"vix_threshold": 20.0, "vix_change_pct": 20.0, "range_multiplier": 2.0}
        with patch("app.core.risk.volatility_kill_switch.fetch_vix", return_value=15.0):
            with patch("app.core.risk.volatility_kill_switch.compute_spy_range", return_value=(1.5, 2.0)):
                with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
                    mock_ticker = MagicMock()
                    # VIX 3-day: 10 -> 11.5 is 15% change (< 20%)
                    mock_ticker.history.return_value = pd.DataFrame({"Close": [9.0, 10.0, 10.5, 11.0, 11.5]})
                    mock_yf.Ticker.return_value = mock_ticker
                    assert is_volatility_high(config) is False

    def test_returns_true_when_vix_3day_change_above_pct(self) -> None:
        """When VIX 3-day change >= vix_change_pct, returns True."""
        import pandas as pd
        config = {"vix_threshold": 30.0, "vix_change_pct": 20.0, "range_multiplier": 2.0}
        with patch("app.core.risk.volatility_kill_switch.fetch_vix", return_value=19.0):
            with patch("app.core.risk.volatility_kill_switch.compute_spy_range", return_value=(1.0, 2.0)):
                with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
                    mock_ticker = MagicMock()
                    # iloc[-1]=12, iloc[-4]=10 -> 20% change
                    mock_ticker.history.return_value = pd.DataFrame({"Close": [8.0, 9.0, 10.0, 11.0, 12.0]})
                    mock_yf.Ticker.return_value = mock_ticker
                    assert is_volatility_high(config) is True

    def test_returns_true_when_spy_range_above_multiplier_atr(self) -> None:
        """When SPY day range > range_multiplier * ATR20, returns True."""
        config = {"vix_threshold": 30.0, "vix_change_pct": 50.0, "range_multiplier": 2.0}
        with patch("app.core.risk.volatility_kill_switch.fetch_vix", return_value=15.0):
            with patch("app.core.risk.volatility_kill_switch.compute_spy_range", return_value=(5.0, 2.0)):
                import pandas as pd
                with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
                    mock_ticker = MagicMock()
                    mock_ticker.history.return_value = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]})
                    mock_yf.Ticker.return_value = mock_ticker
                    assert is_volatility_high(config) is True

    def test_returns_false_when_spy_range_below_multiplier_atr(self) -> None:
        """When SPY day range <= range_multiplier * ATR20, that condition does not trigger."""
        import pandas as pd
        config = {"vix_threshold": 30.0, "vix_change_pct": 50.0, "range_multiplier": 2.0}
        with patch("app.core.risk.volatility_kill_switch.fetch_vix", return_value=15.0):
            with patch("app.core.risk.volatility_kill_switch.compute_spy_range", return_value=(3.0, 2.0)):
                with patch("app.core.risk.volatility_kill_switch.yf", create=True) as mock_yf:
                    mock_ticker = MagicMock()
                    mock_ticker.history.return_value = pd.DataFrame({"Close": [10.0, 11.0, 12.0, 13.0]})
                    mock_yf.Ticker.return_value = mock_ticker
                    assert is_volatility_high(config) is False


class TestRegimeGate:
    """Tests for regime_gate (evaluate_regime_gate)."""

    def test_volatility_high_returns_risk_off_volatility_spike(self) -> None:
        """When is_volatility_high is True, regime is RISK_OFF with reason volatility_spike."""
        from app.core.engine.regime_gate import evaluate_regime_gate
        with patch("app.core.engine.regime_gate.is_volatility_high", return_value=True):
            regime, reason = evaluate_regime_gate("BULL", volatility_config={})
            assert regime == "RISK_OFF"
            assert reason == "volatility_spike"

    def test_volatility_low_returns_base_regime_mapped(self) -> None:
        """When is_volatility_high is False, regime is mapped from base_regime, reason None."""
        from app.core.engine.regime_gate import evaluate_regime_gate
        with patch("app.core.engine.regime_gate.is_volatility_high", return_value=False):
            regime, reason = evaluate_regime_gate("BULL", volatility_config={})
            assert regime == "RISK_ON"
            assert reason is None

    def test_volatility_low_bear_returns_risk_off_no_reason(self) -> None:
        """When volatility low and base is BEAR, returns RISK_OFF, reason None."""
        from app.core.engine.regime_gate import evaluate_regime_gate
        with patch("app.core.engine.regime_gate.is_volatility_high", return_value=False):
            regime, reason = evaluate_regime_gate("BEAR", volatility_config={})
            assert regime == "RISK_OFF"
            assert reason is None

    def test_base_regime_none_maps_to_risk_on_when_volatility_low(self) -> None:
        """When base_regime is None and volatility low, returns RISK_ON."""
        from app.core.engine.regime_gate import evaluate_regime_gate
        with patch("app.core.engine.regime_gate.is_volatility_high", return_value=False):
            regime, reason = evaluate_regime_gate(None, volatility_config={})
            assert regime == "RISK_ON"
            assert reason is None
