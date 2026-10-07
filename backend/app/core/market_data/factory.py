# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market data provider factory.

This module provides a factory function to get the configured market data provider.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


def get_market_data_provider() -> MarketDataProvider:
    """Get configured market data provider. Uses YFinance (no ThetaData dependency)."""
    try:
        from app.core.market_data.yfinance_adapter import YFinanceMarketDataAdapter
        provider = YFinanceMarketDataAdapter()
        logger.info("MarketDataProvider: Using YFinanceMarketDataAdapter")
        return provider
    except ImportError as e:
        logger.warning("MarketDataProvider: YFinance adapter not available: %s", e)
    except Exception as e:
        logger.warning("MarketDataProvider: Failed to initialize YFinance adapter: %s", e)

    raise ValueError(
        "No market data provider available. Install yfinance: pip install yfinance"
    )


__all__ = ["get_market_data_provider"]
