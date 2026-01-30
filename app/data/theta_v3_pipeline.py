# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Theta v3 API pipeline using official patterns.

Based on ThetaData documentation examples:
- basic_request.html: Single endpoint calls
- basic_pipeline.html: list expirations → list strikes → fetch quotes
- concurrent_requests.html: Parallel fetching with semaphore

This module provides:
- list_expirations(symbol) → list[str]
- list_strikes(symbol, expiration) → list[float]
- snapshot_ohlc(symbol, expiration, strike, right) → dict
- fetch_chain(symbol, dte_min, dte_max) → list[dict]
- fetch_chain_async(symbol, dte_min, dte_max) → list[dict]
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.settings import get_theta_base_url, get_theta_timeout

logger = logging.getLogger(__name__)

# Concurrency limit - matches Theta Terminal's shown limit
MAX_CONCURRENT_REQUESTS = 4

# Default timeout for API calls
DEFAULT_TIMEOUT = 30.0


@dataclass
class ThetaHealthStatus:
    """Health check result."""
    healthy: bool
    message: str
    response_time_ms: Optional[float] = None


# =============================================================================
# Low-level API functions (based on Theta's basic_request.html example)
# =============================================================================


def list_expirations(
    symbol: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[str]:
    """List all available expiration dates for a symbol.
    
    GET /option/list/expirations?symbol={symbol}
    
    Returns expiration dates in YYYY-MM-DD format.
    """
    symbol = (symbol or "").upper()
    if not symbol:
        return []
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/list/expirations",
                params={"symbol": symbol, "format": "json"},
            )
            
            if response.status_code != 200:
                logger.warning("list_expirations HTTP %d for %s", response.status_code, symbol)
                return []
            
            data = response.json()
            return _parse_expiration_list(data)
            
    except Exception as e:
        logger.warning("list_expirations failed for %s: %s", symbol, e)
        return []


def list_strikes(
    symbol: str,
    expiration: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[float]:
    """List all available strikes for a symbol and expiration.
    
    GET /option/list/strikes?symbol={symbol}&expiration={expiration}
    
    Returns strike prices as floats.
    """
    symbol = (symbol or "").upper()
    if not symbol or not expiration:
        return []
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    exp_normalized = _normalize_expiration(expiration)
    
    if not exp_normalized:
        return []
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/list/strikes",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "format": "json",
                },
            )
            
            if response.status_code != 200:
                logger.debug("list_strikes HTTP %d for %s %s", response.status_code, symbol, expiration)
                return []
            
            data = response.json()
            return _parse_strike_list(data)
            
    except Exception as e:
        logger.debug("list_strikes failed for %s %s: %s", symbol, expiration, e)
        return []


def snapshot_ohlc(
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch OHLC snapshot for a single option contract.
    
    GET /option/snapshot/ohlc?symbol={symbol}&expiration={exp}&strike={strike}&right={right}
    
    Parameters
    ----------
    symbol : str
        Underlying ticker (e.g., "AAPL")
    expiration : str
        Expiration date (YYYY-MM-DD or YYYYMMDD)
    strike : float
        Strike price
    right : str
        "C" for call, "P" for put
    
    Returns
    -------
    dict or None
        Contract data including bid, ask, IV, Greeks
    """
    symbol = (symbol or "").upper()
    if not symbol or not expiration:
        return None
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    exp_normalized = _normalize_expiration(expiration)
    right_normalized = right.upper() if right else "C"
    
    if right_normalized not in ("C", "P"):
        right_normalized = "C"
    
    # Convert strike to integer in millis (Theta API format)
    # Strike 150.00 becomes 150000
    strike_int = int(strike * 1000)
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/snapshot/ohlc",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "strike": strike_int,
                    "right": right_normalized,
                    "format": "json",
                },
            )
            
            if response.status_code in (204, 404):
                # No data available
                return None
            
            if response.status_code != 200:
                logger.debug("snapshot_ohlc HTTP %d for %s %s %s %s", 
                           response.status_code, symbol, expiration, strike, right)
                return None
            
            data = response.json()
            return _parse_ohlc_response(data, symbol, expiration, strike, right_normalized)
            
    except Exception as e:
        logger.debug("snapshot_ohlc failed for %s %s %s %s: %s", 
                    symbol, expiration, strike, right, e)
        return None


# =============================================================================
# Async versions for concurrent fetching (based on concurrent_requests.html)
# =============================================================================


async def list_expirations_async(
    symbol: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> List[str]:
    """Async version of list_expirations."""
    symbol = (symbol or "").upper()
    if not symbol:
        return []
    
    try:
        async with semaphore:
            response = await client.get(
                "/option/list/expirations",
                params={"symbol": symbol, "format": "json"},
            )
        
        if response.status_code != 200:
            return []
        
        return _parse_expiration_list(response.json())
        
    except Exception as e:
        logger.debug("list_expirations_async failed for %s: %s", symbol, e)
        return []


async def list_strikes_async(
    symbol: str,
    expiration: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> List[float]:
    """Async version of list_strikes."""
    symbol = (symbol or "").upper()
    exp_normalized = _normalize_expiration(expiration)
    
    if not symbol or not exp_normalized:
        return []
    
    try:
        async with semaphore:
            response = await client.get(
                "/option/list/strikes",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "format": "json",
                },
            )
        
        if response.status_code != 200:
            return []
        
        return _parse_strike_list(response.json())
        
    except Exception as e:
        logger.debug("list_strikes_async failed for %s %s: %s", symbol, expiration, e)
        return []


async def snapshot_ohlc_async(
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> Optional[Dict[str, Any]]:
    """Async version of snapshot_ohlc."""
    symbol = (symbol or "").upper()
    exp_normalized = _normalize_expiration(expiration)
    right_normalized = right.upper() if right else "C"
    
    if not symbol or not exp_normalized:
        return None
    
    if right_normalized not in ("C", "P"):
        right_normalized = "C"
    
    strike_int = int(strike * 1000)
    
    try:
        async with semaphore:
            response = await client.get(
                "/option/snapshot/ohlc",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "strike": strike_int,
                    "right": right_normalized,
                    "format": "json",
                },
            )
        
        if response.status_code not in (200,):
            return None
        
        return _parse_ohlc_response(response.json(), symbol, expiration, strike, right_normalized)
        
    except Exception:
        return None


# =============================================================================
# High-level chain fetching (based on basic_pipeline.html)
# =============================================================================


def fetch_chain(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Fetch complete option chain using the basic pipeline pattern.
    
    Pipeline:
    1. list_expirations(symbol) - get all expirations
    2. Filter by DTE window
    3. For each expiration: list_strikes(symbol, expiration)
    4. For each strike: snapshot_ohlc for both call and put
    
    This is the synchronous version - use fetch_chain_async for production.
    """
    symbol = (symbol or "").upper()
    if not symbol:
        return []
    
    url = base_url or get_theta_base_url()
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    
    # Step 1: Get all expirations
    expirations = list_expirations(symbol, base_url=url, timeout=tout)
    if not expirations:
        logger.info("fetch_chain: no expirations for %s", symbol)
        return []
    
    # Step 2: Filter by DTE
    today = date.today()
    valid_expirations: List[str] = []
    for exp_str in expirations:
        exp_date = _parse_date(exp_str)
        if exp_date:
            dte = (exp_date - today).days
            if dte_min <= dte <= dte_max:
                valid_expirations.append(exp_str)
    
    if not valid_expirations:
        logger.info("fetch_chain: no expirations in DTE [%d-%d] for %s (total: %d)", 
                   dte_min, dte_max, symbol, len(expirations))
        return []
    
    logger.info("fetch_chain: %s has %d expirations in DTE [%d-%d]", 
               symbol, len(valid_expirations), dte_min, dte_max)
    
    # Step 3 & 4: For each expiration, get strikes and quotes
    all_contracts: List[Dict[str, Any]] = []
    
    for exp in valid_expirations:
        strikes = list_strikes(symbol, exp, base_url=url, timeout=tout)
        if not strikes:
            continue
        
        logger.debug("fetch_chain: %s %s has %d strikes", symbol, exp, len(strikes))
        
        for strike in strikes:
            # Fetch call
            call_data = snapshot_ohlc(symbol, exp, strike, "C", base_url=url, timeout=tout)
            if call_data:
                all_contracts.append(call_data)
            
            # Fetch put
            put_data = snapshot_ohlc(symbol, exp, strike, "P", base_url=url, timeout=tout)
            if put_data:
                all_contracts.append(put_data)
    
    logger.info("fetch_chain: %s returned %d contracts", symbol, len(all_contracts))
    return all_contracts


async def fetch_chain_async(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_concurrent: int = MAX_CONCURRENT_REQUESTS,
) -> List[Dict[str, Any]]:
    """Async version of fetch_chain with concurrent requests.
    
    Uses asyncio.gather() to parallelize strike-level fetches
    while respecting concurrency limit via semaphore.
    """
    symbol = (symbol or "").upper()
    if not symbol:
        return []
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async with httpx.AsyncClient(base_url=url, timeout=tout) as client:
        # Step 1: Get expirations
        expirations = await list_expirations_async(symbol, client, semaphore)
        if not expirations:
            return []
        
        # Step 2: Filter by DTE
        today = date.today()
        valid_expirations: List[str] = []
        for exp_str in expirations:
            exp_date = _parse_date(exp_str)
            if exp_date:
                dte = (exp_date - today).days
                if dte_min <= dte <= dte_max:
                    valid_expirations.append(exp_str)
        
        if not valid_expirations:
            return []
        
        # Step 3: Get strikes for all expirations (concurrent)
        strike_tasks = [
            list_strikes_async(symbol, exp, client, semaphore)
            for exp in valid_expirations
        ]
        strike_results = await asyncio.gather(*strike_tasks, return_exceptions=True)
        
        # Build list of (expiration, strike) pairs
        quote_requests: List[Tuple[str, float, str]] = []
        for i, result in enumerate(strike_results):
            if isinstance(result, Exception):
                continue
            exp = valid_expirations[i]
            for strike in result:
                quote_requests.append((exp, strike, "C"))
                quote_requests.append((exp, strike, "P"))
        
        if not quote_requests:
            return []
        
        logger.info("fetch_chain_async: %s fetching %d quotes from %d expirations", 
                   symbol, len(quote_requests), len(valid_expirations))
        
        # Step 4: Fetch all quotes (concurrent with semaphore)
        quote_tasks = [
            snapshot_ohlc_async(symbol, exp, strike, right, client, semaphore)
            for exp, strike, right in quote_requests
        ]
        quote_results = await asyncio.gather(*quote_tasks, return_exceptions=True)
        
        # Collect valid results
        all_contracts: List[Dict[str, Any]] = []
        for result in quote_results:
            if isinstance(result, dict):
                all_contracts.append(result)
        
        logger.info("fetch_chain_async: %s returned %d contracts", symbol, len(all_contracts))
        return all_contracts


# =============================================================================
# Health check
# =============================================================================


def check_theta_health(
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> ThetaHealthStatus:
    """Check if Theta Terminal is reachable."""
    import time
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else 10.0
    
    start = time.monotonic()
    try:
        with httpx.Client(timeout=tout) as client:
            # Use a lightweight endpoint
            response = client.get(f"{url}/stock/list/symbols", params={"format": "json"})
            elapsed_ms = (time.monotonic() - start) * 1000
            
            if response.status_code == 200:
                return ThetaHealthStatus(
                    healthy=True,
                    message=f"Theta Terminal OK at {url} ({elapsed_ms:.0f}ms)",
                    response_time_ms=elapsed_ms,
                )
            else:
                return ThetaHealthStatus(
                    healthy=False,
                    message=f"HTTP {response.status_code}",
                    response_time_ms=elapsed_ms,
                )
    except httpx.ConnectError as e:
        return ThetaHealthStatus(healthy=False, message=f"Cannot connect to {url}: {e}")
    except httpx.TimeoutException:
        return ThetaHealthStatus(healthy=False, message=f"Timeout connecting to {url}")
    except Exception as e:
        return ThetaHealthStatus(healthy=False, message=str(e))


# =============================================================================
# Response parsing helpers
# =============================================================================


def _parse_expiration_list(data: Any) -> List[str]:
    """Parse expiration list from API response."""
    expirations: List[str] = []
    
    # Handle {"response": [...]} wrapper
    if isinstance(data, dict):
        data = data.get("response") or data.get("expirations") or []
    
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                expirations.append(item)
            elif isinstance(item, dict):
                exp = item.get("expiration") or item.get("exp") or item.get("date")
                if exp:
                    expirations.append(str(exp))
            elif isinstance(item, int):
                expirations.append(str(item))
    
    # Normalize to YYYY-MM-DD
    normalized: List[str] = []
    for exp in expirations:
        formatted = _format_expiration(exp)
        if formatted:
            normalized.append(formatted)
    
    return sorted(set(normalized))


def _parse_strike_list(data: Any) -> List[float]:
    """Parse strike list from API response."""
    strikes: List[float] = []
    
    # Handle {"response": [...]} wrapper
    if isinstance(data, dict):
        data = data.get("response") or data.get("strikes") or []
    
    if isinstance(data, list):
        for item in data:
            try:
                if isinstance(item, (int, float)):
                    # Strikes may come as millis (150000 = 150.00)
                    val = float(item)
                    if val > 10000:  # Likely in millis
                        val = val / 1000
                    strikes.append(val)
                elif isinstance(item, dict):
                    strike_val = item.get("strike") or item.get("price")
                    if strike_val is not None:
                        val = float(strike_val)
                        if val > 10000:
                            val = val / 1000
                        strikes.append(val)
            except (TypeError, ValueError):
                continue
    
    return sorted(strikes)


def _parse_ohlc_response(
    data: Any,
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
) -> Optional[Dict[str, Any]]:
    """Parse OHLC snapshot response into contract dict."""
    # Handle {"response": [...]} wrapper
    if isinstance(data, dict) and "response" in data:
        rows = data["response"]
        if isinstance(rows, list) and rows:
            row = rows[0] if isinstance(rows[0], dict) else {}
        else:
            return None
    elif isinstance(data, dict):
        row = data
    elif isinstance(data, list) and data:
        row = data[0] if isinstance(data[0], dict) else {}
    else:
        return None
    
    if not isinstance(row, dict):
        return None
    
    # Extract values with fallbacks
    bid = _extract_float(row, ["bid", "bid_price"])
    ask = _extract_float(row, ["ask", "ask_price"])
    mid = None
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
    
    # Calculate DTE
    exp_date = _parse_date(expiration)
    dte = (exp_date - date.today()).days if exp_date else None
    
    return {
        "symbol": symbol,
        "expiration": _format_expiration(expiration),
        "strike": strike,
        "right": right,
        "option_type": "PUT" if right == "P" else "CALL",
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "open": _extract_float(row, ["open"]),
        "high": _extract_float(row, ["high"]),
        "low": _extract_float(row, ["low"]),
        "close": _extract_float(row, ["close", "last"]),
        "iv": _extract_float(row, ["implied_vol", "iv", "implied_volatility"]),
        "delta": _extract_float(row, ["delta"]),
        "gamma": _extract_float(row, ["gamma"]),
        "theta": _extract_float(row, ["theta"]),
        "vega": _extract_float(row, ["vega"]),
        "volume": _extract_int(row, ["volume", "vol"]),
        "open_interest": _extract_int(row, ["open_interest", "oi"]),
        "dte": dte,
    }


def _extract_float(row: Dict[str, Any], keys: List[str]) -> Optional[float]:
    """Extract first valid float from row."""
    for key in keys:
        val = row.get(key)
        if val is not None:
            try:
                f = float(val)
                # Allow zero for Greeks
                if f != 0 or key in ("delta", "gamma", "theta", "vega"):
                    return f
            except (TypeError, ValueError):
                continue
    return None


def _extract_int(row: Dict[str, Any], keys: List[str]) -> Optional[int]:
    """Extract first valid int from row."""
    for key in keys:
        val = row.get(key)
        if val is not None:
            try:
                return int(float(val))
            except (TypeError, ValueError):
                continue
    return None


def _normalize_expiration(exp: Optional[str]) -> str:
    """Normalize expiration to YYYYMMDD format for API calls."""
    if not exp:
        return ""
    exp_str = str(exp).replace("-", "").replace("/", "")
    if len(exp_str) >= 8 and exp_str[:8].isdigit():
        return exp_str[:8]
    return ""


def _format_expiration(exp: Any) -> str:
    """Format expiration to YYYY-MM-DD for display."""
    if not exp:
        return ""
    exp_str = str(exp).replace("-", "").replace("/", "")
    if len(exp_str) >= 8 and exp_str[:8].isdigit():
        return f"{exp_str[:4]}-{exp_str[4:6]}-{exp_str[6:8]}"
    if isinstance(exp, str) and "-" in exp and len(exp) == 10:
        return exp
    return str(exp)


def _parse_date(exp: Any) -> Optional[date]:
    """Parse expiration string to date object."""
    if not exp:
        return None
    if isinstance(exp, date):
        return exp
    exp_str = str(exp).replace("-", "").replace("/", "")
    if len(exp_str) >= 8 and exp_str[:8].isdigit():
        try:
            return date(int(exp_str[:4]), int(exp_str[4:6]), int(exp_str[6:8]))
        except ValueError:
            pass
    return None


# =============================================================================
# Exports
# =============================================================================


__all__ = [
    # Low-level API functions
    "list_expirations",
    "list_strikes",
    "snapshot_ohlc",
    # Async versions
    "list_expirations_async",
    "list_strikes_async",
    "snapshot_ohlc_async",
    # High-level chain fetching
    "fetch_chain",
    "fetch_chain_async",
    # Health check
    "check_theta_health",
    "ThetaHealthStatus",
    # Constants
    "MAX_CONCURRENT_REQUESTS",
]
