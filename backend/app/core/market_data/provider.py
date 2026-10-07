# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market data provider abstraction layer.

This module defines the abstract base class for market data providers.
All market data operations should go through this interface to ensure
consistency and testability.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class OptionContract:
    """Option contract data.
    
    Attributes
    ----------
    symbol:
        Underlying symbol (e.g., "AAPL").
    strike:
        Strike price.
    expiry:
        Expiry date (YYYY-MM-DD format).
    option_type:
        "CALL" or "PUT".
    bid:
        Bid price.
    ask:
        Ask price.
    mid:
        Mid price ((bid + ask) / 2).
    delta:
        Option delta.
    gamma:
        Option gamma (optional).
    theta:
        Option theta (optional).
    vega:
        Option vega (optional).
    iv:
        Implied volatility (optional).
    open_interest:
        Open interest (optional).
    volume:
        Volume (optional).
    """
    symbol: str
    strike: float
    expiry: str  # YYYY-MM-DD
    option_type: str  # CALL | PUT
    bid: float
    ask: float
    mid: float
    delta: float
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    open_interest: Optional[int] = None
    volume: Optional[int] = None


class MarketDataProvider(ABC):
    """Abstract base class for market data providers.
    
    All market data operations should be performed through implementations
    of this class to ensure consistency and testability.
    """
    
    @abstractmethod
    def get_stock_price(self, symbol: str) -> float:
        """Get current stock price.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        
        Returns
        -------
        float
            Current stock price.
        
        Raises
        ------
        ValueError
            If symbol is invalid or data unavailable.
        """
        ...
    
    @abstractmethod
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
        
        Raises
        ------
        ValueError
            If symbol is invalid or insufficient data.
        """
        ...
    
    @abstractmethod
    def get_options_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> List[OptionContract]:
        """Get options chain for a symbol.
        
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
        ValueError
            If symbol is invalid or data unavailable.
        """
        ...
    
    @abstractmethod
    def get_option_mid_price(
        self,
        symbol: str,
        strike: float,
        expiry: str,
        option_type: str,
    ) -> float:
        """Get mid price for a specific option contract.
        
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
        ValueError
            If contract not found or data unavailable.
        """
        ...
    
    @abstractmethod
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
        ...
    
    def get_daily(self, symbol: str, lookback: int = 400) -> "pd.DataFrame":
        """Get daily OHLCV bars for a symbol.
        
        This method provides backward compatibility with the PriceProvider interface.
        Implementations should override this if they can provide historical data.
        
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
        
        Raises
        ------
        NotImplementedError
            If provider does not support historical data.
        ValueError
            If symbol is invalid or data unavailable.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support historical daily data. "
            "Use get_stock_price() and get_ema() for current values."
        )


__all__ = ["MarketDataProvider", "OptionContract"]
