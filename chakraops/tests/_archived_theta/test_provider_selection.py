# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Provider selection (Theta -> yfinance -> SnapshotOnly).
ARCHIVED: Moved from tests/; excluded from pytest via norecursedirs (_archived_theta)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.market.live_market_adapter import _select_provider, fetch_live_market_data, LiveMarketData


def test_select_provider_theta_when_healthy() -> None:
    """When ThetaTerminal health_check returns ok, select Theta."""
    with patch("app.market.providers.ThetaTerminalHttpProvider") as mock_theta:
        mock_theta.return_value.health_check.return_value = (True, "ThetaTerminal OK")
        provider, name = _select_provider()
    assert name == "ThetaTerminal"


def test_select_provider_yfinance_when_theta_down() -> None:
    """When ThetaTerminal is down, select yfinance if healthy."""
    with patch("app.market.providers.ThetaTerminalHttpProvider") as mock_theta:
        mock_theta.return_value.health_check.return_value = (False, "unreachable")
        with patch("app.market.providers.YFinanceProvider") as mock_yf:
            mock_yf.return_value.health_check.return_value = (True, "yfinance OK")
            provider, name = _select_provider()
    assert name == "yfinance (stocks-only)"


def test_select_provider_snapshot_only_when_both_down() -> None:
    """When Theta and yfinance both down, select SnapshotOnly."""
    with patch("app.market.providers.ThetaTerminalHttpProvider") as mock_theta:
        mock_theta.return_value.health_check.return_value = (False, "unreachable")
        with patch("app.market.providers.YFinanceProvider") as mock_yf:
            mock_yf.return_value.health_check.return_value = (False, "no data")
            provider, name = _select_provider()
    assert "SNAPSHOT ONLY" in name


def test_fetch_live_market_data_returns_live_market_data() -> None:
    """fetch_live_market_data returns LiveMarketData with data_source and last_update_utc."""
    with patch("app.market.live_market_adapter._select_provider") as mock_sel:
        mock_prov = type("P", (), {
            "fetch_underlying_prices": lambda s, sym: {"SPY": 450.0},
            "fetch_option_chain_availability": lambda s, sym: {"SPY": True},
        })()
        mock_sel.return_value = (mock_prov, "ThetaTerminal")
        result = fetch_live_market_data(["SPY"])
    assert isinstance(result, LiveMarketData)
    assert result.data_source == "ThetaTerminal"
    assert isinstance(result.last_update_utc, str) and "T" in result.last_update_utc
    assert result.underlying_prices.get("SPY") == 450.0
