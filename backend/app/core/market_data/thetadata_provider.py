# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ThetaData market data provider implementation.

This module provides a ThetaData implementation using HTTP v3 endpoints directly.
ThetaData does NOT provide a pip-installable Python SDK.

IMPORTANT: ThetaData Terminal v3 must be running locally on port 25503.
We use httpx to make HTTP requests to the REST API.

Reference: https://docs.thetadata.us/
Base URL is configured via config.yaml or THETA_REST_URL environment variable.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import httpx

from app.core.settings import get_theta_base_url
from app.core.market_data.provider import MarketDataProvider

logger = logging.getLogger(__name__)


def _get_thetadata_base_url() -> str:
    """Get ThetaData base URL from centralized config."""
    return get_theta_base_url()


# Kept for backward compatibility, but now uses centralized config
THETADATA_BASE_URL = None  # Will be set dynamically


class ProviderDataError(RuntimeError):
    """Raised when provider returns empty or partial data."""
    
    def __init__(self, symbol: str, method: str, reason: str):
        self.symbol = symbol
        self.method = method
        self.reason = reason
        message = f"ProviderDataError: {method}({symbol}) - {reason}"
        super().__init__(message)


class ThetaDataProvider(MarketDataProvider):
    """ThetaData market data provider using HTTP v3 endpoints.
    
    This provider uses HTTP requests to the local ThetaData Terminal v3 REST API.
    The terminal must be running locally on port 25503.
    
    No Python SDK is used - all communication is via HTTP.
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize ThetaData provider.
        
        Parameters
        ----------
        base_url:
            ThetaData Terminal base URL (default: from config.yaml).
        timeout:
            HTTP request timeout in seconds (default: 30.0).
        
        Raises
        ------
        ValueError
            If terminal is not accessible.
        """
        self.base_url = base_url or _get_thetadata_base_url()
        self.timeout = timeout
        
        # Initialize HTTP client
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        
        # Verify terminal is accessible
        try:
            response = self.client.get("/stock/list/symbols", params={"format": "json"})
            response.raise_for_status()
            logger.info(f"ThetaDataProvider: Successfully connected to {self.base_url}")
        except httpx.RequestError as e:
            error_msg = f"Cannot connect to ThetaData Terminal at {self.base_url}. Is the terminal running?"
            logger.error(f"ThetaDataProvider: {error_msg}: {e}")
            raise ValueError(error_msg) from e
        except httpx.HTTPStatusError as e:
            error_msg = f"ThetaData Terminal returned error {e.response.status_code}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise ValueError(error_msg) from e
    
    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, any]] = None,
        format: str = "json",
    ) -> any:
        """Make HTTP request to ThetaData API.
        
        Parameters
        ----------
        endpoint:
            API endpoint path (e.g., "/stock/list/symbols").
        params:
            Optional query parameters.
        format:
            Response format: "json" or "csv" (default: "json").
        
        Returns
        -------
        any
            Parsed response (list for JSON).
        
        Raises
        ------
        ProviderDataError
            If HTTP status != 200 or response is empty.
        RuntimeError
            If request fails.
        """
        if params is None:
            params = {}
        params["format"] = format
        
        try:
            response = self.client.get(endpoint, params=params)
            
            # Error handling: If HTTP status != 200 → raise ProviderDataError
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code} from {endpoint}"
                logger.error(f"ThetaDataProvider: {error_msg} for symbol={params.get('symbol', 'N/A')}")
                raise ProviderDataError(
                    params.get("symbol", ""),
                    endpoint,
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
            
            response.raise_for_status()
            
            if format == "json":
                data = response.json()
                # ThetaData wraps responses in "response" key
                if isinstance(data, dict) and "response" in data:
                    data = data["response"]
                
                # Error handling: If response is empty → raise ProviderDataError
                if not data:
                    error_msg = f"Empty response from {endpoint}"
                    logger.error(f"ThetaDataProvider: {error_msg} for symbol={params.get('symbol', 'N/A')}")
                    raise ProviderDataError(
                        params.get("symbol", ""),
                        endpoint,
                        "Empty response"
                    )
                
                return data
            else:
                return response.text
        
        except ProviderDataError:
            raise
        except httpx.RequestError as e:
            error_msg = f"HTTP request failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg} for endpoint={endpoint}, symbol={params.get('symbol', 'N/A')}")
            raise RuntimeError(error_msg) from e
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code}: {e.response.text[:200]}"
            logger.error(f"ThetaDataProvider: {error_msg} for endpoint={endpoint}, symbol={params.get('symbol', 'N/A')}")
            raise ProviderDataError(
                params.get("symbol", ""),
                endpoint,
                error_msg
            ) from e
        except Exception as e:
            error_msg = f"Failed to parse response: {e}"
            logger.error(f"ThetaDataProvider: {error_msg} for endpoint={endpoint}, symbol={params.get('symbol', 'N/A')}")
            raise RuntimeError(error_msg) from e
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available stock symbols.
        
        Calls: GET /v3/stock/list/symbols?format=json
        
        Returns
        -------
        list[str]
            List of stock symbols (e.g., ["AAPL", "MSFT", "SPY"]).
        
        Raises
        ------
        ProviderDataError
            If request fails or response is empty.
        RuntimeError
            If HTTP request fails.
        """
        try:
            data = self._make_request("/stock/list/symbols", format="json")
            
            # Extract symbols from response
            symbols = []
            for item in data:
                if isinstance(item, dict) and "symbol" in item:
                    symbols.append(item["symbol"])
                elif isinstance(item, str):
                    symbols.append(item)
            
            if not symbols:
                raise ProviderDataError("", "get_available_symbols", "No symbols in response")
            
            logger.info(f"ThetaDataProvider: Fetched {len(symbols)} available symbols")
            return symbols
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_available_symbols() failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e
    
    def get_available_dates(self, symbol: str, request_type: str = "trade") -> List[str]:
        """Get list of available dates for a symbol.
        
        Calls: GET /v3/stock/list/dates/{request_type}?symbol=XYZ&format=json
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        request_type:
            Request type: "trade" or "quote" (default: "trade").
        
        Returns
        -------
        list[str]
            List of available dates in YYYY-MM-DD format.
        
        Raises
        ------
        ProviderDataError
            If request fails or response is empty.
        RuntimeError
            If HTTP request fails.
        """
        if request_type not in ["trade", "quote"]:
            raise ValueError(f"request_type must be 'trade' or 'quote', got: {request_type}")
        
        try:
            endpoint = f"/stock/list/dates/{request_type}"
            data = self._make_request(
                endpoint,
                params={"symbol": symbol},
                format="json"
            )
            
            # Extract dates from response
            dates = []
            for item in data:
                if isinstance(item, dict) and "date" in item:
                    dates.append(item["date"])
                elif isinstance(item, str):
                    dates.append(item)
            
            if not dates:
                raise ProviderDataError(symbol, "get_available_dates", "No dates in response")
            
            logger.info(f"ThetaDataProvider: Fetched {len(dates)} available dates for {symbol}")
            return dates
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_available_dates({symbol}, {request_type}) failed: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise RuntimeError(error_msg) from e
    
    def get_underlying_price(self, symbol: str) -> float:
        """Get underlying stock price using trade or daily endpoints.
        
        This is the canonical method for getting stock prices. It tries:
        1. GET /v3/stock/snapshot/trade?symbol=XYZ&format=json (latest trade price)
        2. Fallback: GET /v3/stock/history/eod?symbol=XYZ&start_date=YYYYMMDD&end_date=YYYYMMDD&format=json (latest close)
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        
        Returns
        -------
        float
            Stock price from trade endpoint or daily close fallback.
        
        Raises
        ------
        ProviderDataError
            If both endpoints fail or return empty data.
        RuntimeError
            If HTTP request fails.
        """
        # Try snapshot trade endpoint first
        try:
            data = self._make_request(
                "/stock/snapshot/trade",
                params={"symbol": symbol},
                format="json"
            )
            
            # Extract price from trade data
            if isinstance(data, list) and len(data) > 0:
                result = data[0]
            elif isinstance(data, dict):
                result = data
            else:
                raise ProviderDataError(symbol, "get_underlying_price", "Invalid trade response format")
            
            # Look for price field (could be "price", "last", "trade_price", etc.)
            price = None
            for field in ["price", "last", "trade_price", "close"]:
                if field in result and result[field] is not None:
                    try:
                        price = float(result[field])
                        if price > 0:
                            logger.info(f"ThetaDataProvider: Fetched {symbol} price from trade endpoint: ${price:.2f}")
                            return price
                    except (ValueError, TypeError):
                        continue
            
            # If no valid price found in trade, try daily fallback
            logger.debug(f"ThetaDataProvider: No valid price in trade response for {symbol}, trying daily fallback")
        
        except (ProviderDataError, RuntimeError) as e:
            # Trade endpoint failed, try daily fallback
            logger.debug(f"ThetaDataProvider: Trade endpoint failed for {symbol}: {e}, trying daily fallback")
        
        # Fallback to history EOD endpoint (use today's date)
        try:
            from datetime import date
            today = date.today()
            today_str = today.strftime("%Y%m%d")
            
            data = self._make_request(
                "/stock/history/eod",
                params={
                    "symbol": symbol,
                    "start_date": today_str,
                    "end_date": today_str
                },
                format="json"
            )
            
            # Extract close price from daily data
            if isinstance(data, list) and len(data) > 0:
                result = data[0]
            elif isinstance(data, dict):
                result = data
            else:
                raise ProviderDataError(symbol, "get_underlying_price", "Invalid daily response format")
            
            # Look for close price
            price = None
            for field in ["close", "price", "last"]:
                if field in result and result[field] is not None:
                    try:
                        price = float(result[field])
                        if price > 0:
                            logger.info(f"ThetaDataProvider: Fetched {symbol} price from EOD endpoint (fallback): ${price:.2f}")
                            return price
                    except (ValueError, TypeError):
                        continue
            
            raise ProviderDataError(
                symbol,
                "get_underlying_price",
                f"No valid price found in daily response. Fields: {list(result.keys())}"
            )
        
        except ProviderDataError:
            raise
        except Exception as e:
            error_msg = f"get_underlying_price({symbol}) failed: Both trade and daily endpoints failed. Last error: {e}"
            logger.error(f"ThetaDataProvider: {error_msg}")
            raise ProviderDataError(symbol, "get_underlying_price", f"Both endpoints failed: {e}") from e
    
    # Required abstract methods from MarketDataProvider
    # All use get_underlying_price() as the canonical source
    
    def get_stock_price(self, symbol: str) -> float:
        """Get current stock price.
        
        Uses get_underlying_price() as the canonical source.
        
        Parameters
        ----------
        symbol:
            Stock symbol (e.g., "AAPL").
        
        Returns
        -------
        float
            Current stock price.
        """
        return self.get_underlying_price(symbol)
    
    def get_ema(self, symbol: str, period: int) -> float:
        """Get current EMA value (stub - not implemented yet)."""
        raise NotImplementedError("get_ema() not yet implemented")
    
    def get_options_chain(
        self,
        symbol: str,
        expiry: Optional[str] = None,
    ) -> List:
        """Get options chain (stub - not implemented yet)."""
        raise NotImplementedError("get_options_chain() not yet implemented")
    
    def get_option_mid_price(
        self,
        symbol: str,
        strike: float,
        expiry: str,
        option_type: str,
    ) -> float:
        """Get option mid price (stub - not implemented yet)."""
        raise NotImplementedError("get_option_mid_price() not yet implemented")
    
    def get_dte(self, expiry: str) -> int:
        """Calculate days to expiration (stub - basic implementation)."""
        from datetime import date, datetime
        try:
            expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            today = date.today()
            dte = (expiry_date - today).days
            return max(0, dte)
        except ValueError as e:
            raise ValueError(f"Invalid expiry format '{expiry}'. Expected YYYY-MM-DD.") from e
    
    def get_daily(self, symbol: str, lookback: int = 400):
        """Get daily OHLCV bars (stub - not implemented yet)."""
        raise NotImplementedError("get_daily() not yet implemented")
    
    def __del__(self):
        """Close HTTP client on cleanup."""
        if hasattr(self, "client"):
            try:
                self.client.close()
            except Exception:
                pass


__all__ = ["ThetaDataProvider", "ProviderDataError"]
