# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market data provider factory.

This module provides a factory function to get the configured market data provider.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from app.core.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


def get_market_data_provider() -> MarketDataProvider:
    """Get configured market data provider.
    
    This function attempts to initialize ThetaDataProvider first. If that fails,
    it falls back to other providers or raises an error.
    
    Returns
    -------
    MarketDataProvider
        Configured market data provider instance.
    
    Raises
    ------
    ValueError
        If no provider can be initialized.
    """
    # Try ThetaData first (primary provider)
    if os.getenv("THETADATA_USERNAME") and os.getenv("THETADATA_PASSWORD"):
        try:
            from app.core.market_data.thetadata_provider import ThetaDataProvider
            provider = ThetaDataProvider()
            logger.info("MarketDataProvider: Using ThetaDataProvider")
            return provider
        except ImportError as e:
            logger.warning(f"MarketDataProvider: ThetaData not available: {e}")
        except Exception as e:
            logger.warning(f"MarketDataProvider: Failed to initialize ThetaDataProvider: {e}")
    
    # No provider available
    raise ValueError(
        "No market data provider available. "
        "Set THETADATA_USERNAME and THETADATA_PASSWORD environment variables, "
        "or install thetadata package: pip install thetadata"
    )


__all__ = ["get_market_data_provider"]
