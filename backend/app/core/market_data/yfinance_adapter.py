# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""YFinance adapter for MarketDataProvider interface.

This module provides an adapter that wraps YFinanceProvider (PriceProvider)
to implement the MarketDataProvider interface.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

import pandas as pd

from app.core.market_data.provider import MarketDataProvider, OptionContract
from app.data.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)


class YFinanceMarketDataAdapter(MarketDataProvider):
    """Adapter that wraps YFinanceProvider to implement MarketDataProvider.
    
    This adapter provides a MarketDataProvider interface using yfinance
    as the underlying data source. Some methods are stubbed or have limited
    functionality compared to ThetaDataProvider.
    """
    
    def __init__(self) -> None:
        """Initialize YFinance adapter."""
        self.price_provider = YFinanceProvider()
        logger.info("YFinanceMarketDataAdapter: Initialized")
    
    def get_stock_price(self, symbol: str) -> float:
        """Get current stock price from latest daily bar.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        
        Returns
        -------
        float
            Current stock price (latest close).
        """
        try:
            # Get recent daily data and use the latest close
            df = self.price_provider.get_daily(symbol, lookback=5)
            if df.empty:
                raise ValueError(f"No data available for {symbol}")
            latest_close = float(df.iloc[-1]["close"])
            logger.debug(f"YFinanceMarketDataAdapter: Fetched {symbol} price: ${latest_close:.2f}")
            return latest_close
        except Exception as e:
            raise ValueError(f"Failed to get stock price for {symbol}: {e}") from e
    
    def get_ema(self, symbol: str, period: int) -> float:
        """Get current EMA value.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        period:
            EMA period (e.g., 50, 200).
        
        Returns
        -------
        float
            Current EMA value.
        """
        try:
            # Get enough data to calculate EMA
            lookback = max(period * 2, 400)
            df = self.price_provider.get_daily(symbol, lookback=lookback)
            if df.empty or len(df) < period:
                raise ValueError(f"Insufficient data for {period}-period EMA on {symbol}")
            
            # Calculate EMA
            df["ema"] = df["close"].ewm(span=period, adjust=False).mean()
            latest_ema = float(df.iloc[-1]["ema"])
            logger.debug(f"YFinanceMarketDataAdapter: Calculated {period}-period EMA for {symbol}: ${latest_ema:.2f}")
            return latest_ema
        except Exception as e:
            raise ValueError(f"Failed to get EMA for {symbol}: {e}") from e
    
    def get_options_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> List[OptionContract]:
        """Get options chain (stub - not fully implemented).
        
        Note: yfinance has limited options data support. This method
        is stubbed and will raise NotImplementedError.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        expiry:
            Optional expiry date (YYYY-MM-DD). If None, returns all expiries.
        
        Returns
        -------
        list[OptionContract]
            List of option contracts.
        
        Raises
        ------
        NotImplementedError
            Options chain not fully supported via yfinance.
        """
        raise NotImplementedError(
            "get_options_chain() not fully implemented for YFinance adapter. "
            "Use ThetaDataProvider for options data."
        )
    
    def get_option_mid_price(
        self,
        symbol: str,
        strike: float,
        expiry: str,
        option_type: str,
    ) -> float:
        """Get option mid price (stub - not fully implemented).
        
        Note: yfinance has limited options data support. This method
        is stubbed and will raise NotImplementedError.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        strike:
            Strike price.
        expiry:
            Expiry date (YYYY-MM-DD).
        option_type:
            "CALL" or "PUT".
        
        Returns
        -------
        float
            Mid price ((bid + ask) / 2).
        
        Raises
        ------
        NotImplementedError
            Option pricing not fully supported via yfinance.
        """
        raise NotImplementedError(
            "get_option_mid_price() not fully implemented for YFinance adapter. "
            "Use ThetaDataProvider for options data."
        )
    
    def get_dte(self, expiry: str) -> int:
        """Calculate days to expiration.
        
        Parameters
        ----------
        expiry:
            Expiry date (YYYY-MM-DD).
        
        Returns
        -------
        int
            Days to expiration (0 if expired).
        """
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            today = date.today()
            dte = (expiry_date - today).days
            return max(0, dte)
        except ValueError as e:
            raise ValueError(f"Invalid expiry format '{expiry}'. Expected YYYY-MM-DD.") from e
    
    def get_daily(self, symbol: str, lookback: int = 400) -> pd.DataFrame:
        """Get daily OHLCV bars for a symbol.
        
        This method delegates to the underlying YFinanceProvider.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        lookback:
            Maximum number of most-recent daily bars to return.
        
        Returns
        -------
        pandas.DataFrame
            Columns: date (datetime), open, high, low, close, volume.
            Rows sorted ascending by date (newest last).
        """
        return self.price_provider.get_daily(symbol, lookback=lookback)


__all__ = ["YFinanceMarketDataAdapter"]
