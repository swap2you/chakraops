# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ThetaData market data provider implementation.

This module provides a ThetaData implementation of the MarketDataProvider interface.
It uses the official thetadata Python client library for authentication and data fetching.

IMPORTANT: Credentials must be provided via environment variables:
- THETADATA_USERNAME
- THETADATA_PASSWORD

Do NOT hardcode credentials in this file.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

from app.core.market_data.provider import MarketDataProvider, OptionContract

logger = logging.getLogger(__name__)


class ProviderDataError(RuntimeError):
    """Raised when provider returns empty or partial data."""
    
    def __init__(self, symbol: str, method: str, reason: str):
        self.symbol = symbol
        self.method = method
        self.reason = reason
        message = f"ProviderDataError: {method}({symbol}) - {reason}"
        super().__init__(message)

# In-memory cache with TTL
_CACHE_TTL_SECONDS = 60
_cache: Dict[str, Tuple[any, datetime]] = {}


def _get_cache_key(prefix: str, *args) -> str:
    """Generate cache key from prefix and arguments."""
    return f"{prefix}:{':'.join(str(arg) for arg in args)}"


def _is_cache_valid(cached_time: datetime) -> bool:
    """Check if cached entry is still valid."""
    age = datetime.now(timezone.utc) - cached_time
    return age.total_seconds() < _CACHE_TTL_SECONDS


def _get_from_cache(key: str) -> Optional[any]:
    """Get value from cache if valid."""
    if key in _cache:
        value, cached_time = _cache[key]
        if _is_cache_valid(cached_time):
            return value
        # Expired, remove from cache
        del _cache[key]
    return None


def _set_cache(key: str, value: any) -> None:
    """Set value in cache with current timestamp."""
    _cache[key] = (value, datetime.now(timezone.utc))


class ThetaDataProvider(MarketDataProvider):
    """ThetaData market data provider.
    
    This provider uses the official thetadata Python client library to fetch
    real-time and historical market data. All responses are cached in-memory
    with a 60-second TTL to avoid overuse of API calls.
    """
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Initialize ThetaData provider.
        
        Parameters
        ----------
        username:
            ThetaData username. If not provided, uses THETADATA_USERNAME from environment.
        password:
            ThetaData password. If not provided, uses THETADATA_PASSWORD from environment.
        
        Raises
        ------
        ValueError
            If credentials are missing or invalid.
        ImportError
            If thetadata package is not installed.
        """
        self.username = username or os.getenv("THETADATA_USERNAME")
        self.password = password or os.getenv("THETADATA_PASSWORD")
        
        if not self.username or not self.password:
            raise ValueError(
                "ThetaData credentials not provided. "
                "Set THETADATA_USERNAME and THETADATA_PASSWORD environment variables."
            )
        
        # Import thetadata client
        try:
            from thetadata import ThetaClient
        except ImportError:
            raise ImportError(
                "thetadata package is not installed. "
                "Install it with: pip install thetadata"
            )
        
        # Initialize client
        try:
            self.client = ThetaClient(username=self.username, password=self.password)
            logger.info("ThetaDataProvider: Successfully authenticated")
        except Exception as e:
            logger.error(f"ThetaDataProvider: Authentication failed: {e}")
            raise ValueError(f"ThetaData authentication failed: {e}") from e
    
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
        cache_key = _get_cache_key("price", symbol)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"ThetaDataProvider: Using cached price for {symbol}")
            return cached
        
        try:
            # Fetch last trade price
            # NOTE: Actual ThetaData API method names may differ - adjust after smoke test
            price = self.client.get_last_price(symbol)
            
            if price is None:
                error_msg = f"get_stock_price({symbol}) returned None"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_stock_price", "Price is None")
            
            try:
                price_float = float(price)
            except (ValueError, TypeError) as e:
                error_msg = f"get_stock_price({symbol}) returned non-numeric value: {price}"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_stock_price", f"Invalid price type: {type(price)}") from e
            
            if price_float <= 0:
                error_msg = f"get_stock_price({symbol}) returned invalid price: {price_float}"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_stock_price", f"Price <= 0: {price_float}")
            
            _set_cache(cache_key, price_float)
            logger.info(f"ThetaDataProvider: Fetched price for {symbol}: ${price_float:.2f}")
            return price_float
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_stock_price({symbol}) failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e
    
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
        cache_key = _get_cache_key("ema", symbol, period)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"ThetaDataProvider: Using cached EMA{period} for {symbol}")
            return cached
        
        try:
            # Fetch historical data to calculate EMA
            # NOTE: Actual ThetaData API method names may differ - adjust after smoke test
            bars = self.client.get_historical_bars(
                symbol=symbol,
                start_date=date.today() - timedelta(days=period * 2),
                end_date=date.today(),
                interval="1D",
            )
            
            if bars is None:
                error_msg = f"get_ema({symbol}, {period}) returned None for bars"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_ema", "Historical bars is None")
            
            if not bars:
                error_msg = f"get_ema({symbol}, {period}) returned empty bars list"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_ema", "Empty historical bars")
            
            if len(bars) < period:
                error_msg = f"get_ema({symbol}, {period}) insufficient data: need {period}, got {len(bars)}"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_ema", f"Insufficient bars: {len(bars)} < {period}")
            
            # Calculate EMA from close prices
            df = pd.DataFrame(bars)
            df = df.sort_values("date" if "date" in df.columns else df.columns[0])
            closes = df["close"].values if "close" in df.columns else df.iloc[:, -1].values
            
            # Calculate EMA
            ema = closes[-1]  # Start with first close
            multiplier = 2.0 / (period + 1)
            for close in closes[1:]:
                ema = (close - ema) * multiplier + ema
            
            _set_cache(cache_key, ema)
            logger.info(f"ThetaDataProvider: Calculated EMA{period} for {symbol}: ${ema:.2f}")
            return float(ema)
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_ema({symbol}, {period}) failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e
    
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
        cache_key = _get_cache_key("chain", symbol, expiry or "all")
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"ThetaDataProvider: Using cached chain for {symbol}")
            return cached
        
        try:
            # Fetch options chain from ThetaData
            # NOTE: Actual ThetaData API method names may differ - adjust after smoke test
            chain_data = self.client.get_options_chain(
                symbol=symbol,
                expiry=expiry,
            )
            
            if chain_data is None:
                error_msg = f"get_options_chain({symbol}, {expiry}) returned None"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_options_chain", "Chain data is None")
            
            if not chain_data:
                error_msg = f"get_options_chain({symbol}, {expiry}) returned empty chain"
                logger.warning(f"ThetaDataProvider: {error_msg}")
                # Empty chain is acceptable (no options available), return empty list
                return []
            
            # Convert to OptionContract objects
            contracts: List[OptionContract] = []
            for contract_data in chain_data:
                try:
                    bid = float(contract_data.get("bid", 0) or 0)
                    ask = float(contract_data.get("ask", 0) or 0)
                    mid = (bid + ask) / 2.0 if (bid > 0 and ask > 0) else 0.0
                    
                    contract = OptionContract(
                        symbol=symbol,
                        strike=float(contract_data.get("strike", 0)),
                        expiry=contract_data.get("expiry", ""),
                        option_type=contract_data.get("type", "PUT").upper(),
                        bid=bid,
                        ask=ask,
                        mid=mid,
                        delta=float(contract_data.get("delta", 0) or 0),
                        gamma=float(contract_data.get("gamma", 0) or 0) if contract_data.get("gamma") else None,
                        theta=float(contract_data.get("theta", 0) or 0) if contract_data.get("theta") else None,
                        vega=float(contract_data.get("vega", 0) or 0) if contract_data.get("vega") else None,
                        iv=float(contract_data.get("iv", 0) or 0) if contract_data.get("iv") else None,
                        open_interest=int(contract_data.get("open_interest", 0) or 0) if contract_data.get("open_interest") else None,
                        volume=int(contract_data.get("volume", 0) or 0) if contract_data.get("volume") else None,
                    )
                    contracts.append(contract)
                except Exception as e:
                    logger.warning(f"ThetaDataProvider: Failed to parse contract: {e}")
                    continue
            
            _set_cache(cache_key, contracts)
            logger.info(f"ThetaDataProvider: Fetched {len(contracts)} contracts for {symbol}")
            return contracts
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_options_chain({symbol}, {expiry}) failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e
    
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
        cache_key = _get_cache_key("mid", symbol, strike, expiry, option_type)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"ThetaDataProvider: Using cached mid price for {symbol} {strike} {expiry} {option_type}")
            return cached
        
        try:
            # Fetch options chain and find matching contract
            chain = self.get_options_chain(symbol, expiry=expiry)
            
            option_type_upper = option_type.upper()
            matching_contracts = [
                c for c in chain
                if c.strike == strike and c.option_type == option_type_upper
            ]
            
            if not matching_contracts:
                raise ValueError(
                    f"Option contract not found: {symbol} {strike} {expiry} {option_type}"
                )
            
            contract = matching_contracts[0]
            mid_price = contract.mid
            
            if mid_price <= 0:
                raise ValueError(
                    f"Invalid mid price for {symbol} {strike} {expiry} {option_type}: {mid_price}"
                )
            
            _set_cache(cache_key, mid_price)
            logger.info(
                f"ThetaDataProvider: Fetched mid price for {symbol} {strike} {expiry} {option_type}: ${mid_price:.2f}"
            )
            return mid_price
        
        except Exception as e:
            logger.error(
                f"ThetaDataProvider: Failed to fetch mid price for {symbol} {strike} {expiry} {option_type}: {e}"
            )
            raise ValueError(
                f"Failed to fetch mid price for {symbol} {strike} {expiry} {option_type}: {e}"
            ) from e
    
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
            logger.error(f"ThetaDataProvider: Invalid expiry format '{expiry}': {e}")
            raise ValueError(f"Invalid expiry format '{expiry}'. Expected YYYY-MM-DD.") from e
    
    def get_daily(self, symbol: str, lookback: int = 400) -> pd.DataFrame:
        """Get daily OHLCV bars for a symbol.
        
        This method provides backward compatibility with the PriceProvider interface.
        
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
        ValueError
            If symbol is invalid or data unavailable.
        """
        cache_key = _get_cache_key("daily", symbol, lookback)
        cached = _get_from_cache(cache_key)
        if cached is not None:
            logger.debug(f"ThetaDataProvider: Using cached daily bars for {symbol}")
            return cached
        
        try:
            # Fetch historical daily bars
            # NOTE: Actual ThetaData API method names may differ - adjust after smoke test
            start_date = date.today() - timedelta(days=lookback * 2)
            bars = self.client.get_historical_bars(
                symbol=symbol,
                start_date=start_date,
                end_date=date.today(),
                interval="1D",
            )
            
            if bars is None:
                error_msg = f"get_daily({symbol}, {lookback}) returned None for bars"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_daily", "Historical bars is None")
            
            if not bars:
                error_msg = f"get_daily({symbol}, {lookback}) returned empty bars list"
                logger.error(f"ThetaDataProvider: {error_msg}")
                raise ProviderDataError(symbol, "get_daily", "Empty historical bars")
            
            # Convert to DataFrame
            df = pd.DataFrame(bars)
            
            # Normalize column names
            column_mapping = {
                "date": "date",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            
            # Map columns (handle different possible column names)
            for old_col, new_col in column_mapping.items():
                if old_col not in df.columns:
                    # Try alternative names
                    alternatives = {
                        "date": ["timestamp", "time", "datetime"],
                        "open": ["o"],
                        "high": ["h"],
                        "low": ["l"],
                        "close": ["c"],
                        "volume": ["v", "vol"],
                    }
                    for alt in alternatives.get(old_col, []):
                        if alt in df.columns:
                            df = df.rename(columns={alt: new_col})
                            break
            
            # Ensure required columns exist
            required_cols = ["date", "open", "high", "low", "close", "volume"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                raise ValueError(
                    f"ThetaData response missing required columns: {missing}. "
                    f"Available columns: {list(df.columns)}"
                )
            
            # Convert date column to datetime
            if df["date"].dtype != "datetime64[ns]":
                df["date"] = pd.to_datetime(df["date"])
            
            # Sort by date ascending (newest last)
            df = df.sort_values("date", ascending=True).reset_index(drop=True)
            
            # Trim to requested lookback
            if len(df) > lookback:
                df = df.tail(lookback).reset_index(drop=True)
            
            # Select only required columns
            df = df[required_cols].copy()
            
            _set_cache(cache_key, df)
            logger.info(f"ThetaDataProvider: Fetched {len(df)} daily bars for {symbol}")
            return df
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_daily({symbol}, {lookback}) failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e


__all__ = ["ThetaDataProvider", "ProviderDataError"]
