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


def snapshot_quote(
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch quote snapshot for a single option contract.
    
    GET /option/snapshot/quote?symbol={symbol}&expiration={exp}&strike={strike}&right={right}
    
    This is an alternative to snapshot_ohlc that may work with different subscriptions.
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
    
    strike_int = int(strike * 1000)
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/snapshot/quote",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "strike": strike_int,
                    "right": right_normalized,
                    "format": "json",
                },
            )
            
            if response.status_code in (204, 404):
                return None
            
            if response.status_code != 200:
                logger.debug("snapshot_quote HTTP %d for %s %s %s %s", 
                           response.status_code, symbol, expiration, strike, right)
                return None
            
            data = response.json()
            return _parse_quote_response(data, symbol, expiration, strike, right_normalized)
            
    except Exception as e:
        logger.debug("snapshot_quote failed for %s %s %s %s: %s", 
                    symbol, expiration, strike, right, e)
        return None


def snapshot_ohlc_bulk(
    symbol: str,
    expiration: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Fetch OHLC for ALL contracts at an expiration (bulk, no strike param).
    
    GET /option/snapshot/ohlc?symbol={symbol}&expiration={exp}
    
    This may return all strikes at once if the API supports it.
    """
    symbol = (symbol or "").upper()
    if not symbol or not expiration:
        return []
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    exp_normalized = _normalize_expiration(expiration)
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/snapshot/ohlc",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "format": "json",
                },
            )
            
            if response.status_code in (204, 404, 400):
                return []
            
            if response.status_code != 200:
                logger.debug("snapshot_ohlc_bulk HTTP %d for %s %s", 
                           response.status_code, symbol, expiration)
                return []
            
            data = response.json()
            return _parse_bulk_response(data, symbol, expiration)
            
    except Exception as e:
        logger.debug("snapshot_ohlc_bulk failed for %s %s: %s", symbol, expiration, e)
        return []


def snapshot_quote_bulk(
    symbol: str,
    expiration: str,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Fetch quote for ALL contracts at an expiration (bulk, no strike param).
    
    GET /option/snapshot/quote?symbol={symbol}&expiration={exp}
    
    This may return all strikes at once if the API supports it.
    """
    symbol = (symbol or "").upper()
    if not symbol or not expiration:
        return []
    
    url = (base_url or get_theta_base_url()).rstrip("/")
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    exp_normalized = _normalize_expiration(expiration)
    
    try:
        with httpx.Client(timeout=tout) as client:
            response = client.get(
                f"{url}/option/snapshot/quote",
                params={
                    "symbol": symbol,
                    "expiration": exp_normalized,
                    "format": "json",
                },
            )
            
            if response.status_code in (204, 404, 400):
                return []
            
            if response.status_code != 200:
                logger.debug("snapshot_quote_bulk HTTP %d for %s %s", 
                           response.status_code, symbol, expiration)
                return []
            
            data = response.json()
            return _parse_bulk_response(data, symbol, expiration)
            
    except Exception as e:
        logger.debug("snapshot_quote_bulk failed for %s %s: %s", symbol, expiration, e)
        return []


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


def _filter_strikes_near_atm(
    strikes: List[float],
    underlying_price: Optional[float] = None,
    strike_limit: int = 30,
) -> List[float]:
    """Filter strikes to focus on near-the-money options.
    
    If underlying_price is provided, center the window around ATM.
    Otherwise, take strikes from the middle of the range.
    """
    if not strikes or strike_limit <= 0:
        return strikes
    
    if len(strikes) <= strike_limit:
        return strikes
    
    sorted_strikes = sorted(strikes)
    
    if underlying_price and underlying_price > 0:
        # Find strikes closest to underlying price
        # Center the window around ATM
        atm_idx = 0
        min_diff = float('inf')
        for i, s in enumerate(sorted_strikes):
            diff = abs(s - underlying_price)
            if diff < min_diff:
                min_diff = diff
                atm_idx = i
        
        # Take strike_limit/2 on each side of ATM
        half = strike_limit // 2
        start_idx = max(0, atm_idx - half)
        end_idx = min(len(sorted_strikes), start_idx + strike_limit)
        
        # Adjust if we hit the end
        if end_idx - start_idx < strike_limit:
            start_idx = max(0, end_idx - strike_limit)
        
        return sorted_strikes[start_idx:end_idx]
    else:
        # No underlying price - take from the middle
        mid = len(sorted_strikes) // 2
        half = strike_limit // 2
        start_idx = max(0, mid - half)
        end_idx = min(len(sorted_strikes), start_idx + strike_limit)
        return sorted_strikes[start_idx:end_idx]


def fetch_chain(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    endpoint: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Fetch complete option chain using bulk endpoints (one API call per expiration).
    
    RECOMMENDED: Use "quote_bulk" or "ohlc_bulk" for Standard subscriptions.
    Per-strike endpoints are deprecated and may not work.
    
    Endpoint modes:
    - "quote_bulk": Fetch via /option/snapshot/quote (recommended, fastest)
    - "ohlc_bulk": Fetch via /option/snapshot/ohlc (includes OHLC data)
    - "auto": Try quote_bulk first, then ohlc_bulk
    - "ohlc_per_strike" / "quote_per_strike": Legacy per-strike (slow, may not work)
    
    Run `python scripts/test_theta_chain.py AAPL` to verify which endpoint works.
    
    Parameters
    ----------
    symbol : str
        Underlying ticker (e.g., "AAPL")
    dte_min : int
        Minimum days to expiration (default: 7)
    dte_max : int
        Maximum days to expiration (default: 45)
    endpoint : str, optional
        Endpoint mode. If None, reads from config.yaml (theta.endpoint) or THETA_ENDPOINT env var.
    """
    from app.core.settings import get_theta_endpoint, get_theta_strike_limit
    
    symbol = (symbol or "").upper()
    if not symbol:
        return []
    
    url = base_url or get_theta_base_url()
    tout = timeout if timeout is not None else DEFAULT_TIMEOUT
    endpoint_mode = endpoint or get_theta_endpoint()
    
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
    
    logger.info("fetch_chain: %s has %d expirations in DTE [%d-%d], mode=%s", 
               symbol, len(valid_expirations), dte_min, dte_max, endpoint_mode)
    
    all_contracts: List[Dict[str, Any]] = []
    
    # BULK ENDPOINTS (recommended)
    # Try quote_bulk first (fastest and most compatible)
    if endpoint_mode in ("quote_bulk", "auto"):
        for exp in valid_expirations:
            contracts = snapshot_quote_bulk(symbol, exp, base_url=url, timeout=tout)
            if contracts:
                all_contracts.extend(contracts)
        
        if all_contracts:
            logger.info("fetch_chain: %s returned %d contracts via quote_bulk", symbol, len(all_contracts))
            return all_contracts
        elif endpoint_mode == "quote_bulk":
            logger.warning("fetch_chain: quote_bulk returned no data for %s", symbol)
            return []
        # If auto mode, fall through to try ohlc_bulk
    
    # Try ohlc_bulk
    if endpoint_mode in ("ohlc_bulk", "auto"):
        for exp in valid_expirations:
            contracts = snapshot_ohlc_bulk(symbol, exp, base_url=url, timeout=tout)
            if contracts:
                all_contracts.extend(contracts)
        
        if all_contracts:
            logger.info("fetch_chain: %s returned %d contracts via ohlc_bulk", symbol, len(all_contracts))
            return all_contracts
        elif endpoint_mode == "ohlc_bulk":
            logger.warning("fetch_chain: ohlc_bulk returned no data for %s", symbol)
            return []
        # If auto mode, fall through to per-strike (legacy)
    
    # PER-STRIKE ENDPOINTS (legacy, may not work for Standard subscriptions)
    if endpoint_mode in ("ohlc_per_strike", "quote_per_strike", "auto"):
        use_quote = endpoint_mode == "quote_per_strike"
        fetch_func = snapshot_quote if use_quote else snapshot_ohlc
        func_name = "quote" if use_quote else "ohlc"
        strike_limit = get_theta_strike_limit()
        
        logger.warning("fetch_chain: using legacy per-strike mode (%s) for %s - this may be slow", func_name, symbol)
        
        for exp in valid_expirations:
            strikes = list_strikes(symbol, exp, base_url=url, timeout=tout)
            if not strikes:
                continue
            
            # Filter to near-ATM strikes
            filtered_strikes = _filter_strikes_near_atm(strikes, None, strike_limit)
            
            for strike in filtered_strikes:
                call_data = fetch_func(symbol, exp, strike, "C", base_url=url, timeout=tout)
                if call_data:
                    all_contracts.append(call_data)
                
                put_data = fetch_func(symbol, exp, strike, "P", base_url=url, timeout=tout)
                if put_data:
                    all_contracts.append(put_data)
        
        if all_contracts:
            logger.info("fetch_chain: %s returned %d contracts via %s_per_strike", symbol, len(all_contracts), func_name)
        else:
            logger.warning("fetch_chain: per-strike mode returned no data for %s", symbol)
    
    return all_contracts


async def fetch_chain_async(
    symbol: str,
    dte_min: int = 7,
    dte_max: int = 45,
    strike_limit: int = 30,
    underlying_price: Optional[float] = None,
    base_url: Optional[str] = None,
    timeout: Optional[float] = None,
    max_concurrent: int = MAX_CONCURRENT_REQUESTS,
) -> List[Dict[str, Any]]:
    """Async version of fetch_chain with concurrent requests.
    
    Uses asyncio.gather() to parallelize strike-level fetches
    while respecting concurrency limit via semaphore.
    
    Parameters
    ----------
    symbol : str
        Underlying ticker
    dte_min : int
        Minimum days to expiration (default: 7)
    dte_max : int
        Maximum days to expiration (default: 45)
    strike_limit : int
        Max strikes per expiration, centered on ATM (default: 30)
    underlying_price : float, optional
        Current stock price for ATM centering
    max_concurrent : int
        Max concurrent API requests (default: 4)
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
        
        # Build list of (expiration, strike) pairs with ATM filtering
        quote_requests: List[Tuple[str, float, str]] = []
        for i, result in enumerate(strike_results):
            if isinstance(result, Exception):
                continue
            exp = valid_expirations[i]
            # Filter to near-ATM strikes
            filtered_strikes = _filter_strikes_near_atm(result, underlying_price, strike_limit)
            for strike in filtered_strikes:
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


def _parse_quote_response(
    data: Any,
    symbol: str,
    expiration: str,
    strike: float,
    right: str,
) -> Optional[Dict[str, Any]]:
    """Parse quote snapshot response into contract dict.
    
    Similar to OHLC but quote endpoint may have different field names.
    """
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
    
    bid = _extract_float(row, ["bid", "bid_price", "bidPrice"])
    ask = _extract_float(row, ["ask", "ask_price", "askPrice"])
    mid = None
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
    
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
        "close": _extract_float(row, ["close", "last", "price"]),
        "iv": _extract_float(row, ["implied_vol", "iv", "implied_volatility", "impliedVol"]),
        "delta": _extract_float(row, ["delta"]),
        "gamma": _extract_float(row, ["gamma"]),
        "theta": _extract_float(row, ["theta"]),
        "vega": _extract_float(row, ["vega"]),
        "volume": _extract_int(row, ["volume", "vol"]),
        "open_interest": _extract_int(row, ["open_interest", "oi", "openInterest"]),
        "dte": dte,
    }


def _parse_bulk_response(
    data: Any,
    symbol: str,
    expiration: str,
) -> List[Dict[str, Any]]:
    """Parse bulk response (multiple contracts) into list of contract dicts."""
    contracts: List[Dict[str, Any]] = []
    
    if isinstance(data, dict) and "response" in data:
        rows = data["response"]
    elif isinstance(data, list):
        rows = data
    else:
        return []
    
    if not isinstance(rows, list):
        return []
    
    for row in rows:
        if not isinstance(row, dict):
            continue
        
        # Extract strike - may be in millis
        strike = _extract_float(row, ["strike"])
        if strike is None:
            continue
        if strike > 10000:  # Likely in millis
            strike = strike / 1000
        
        # Get right (C/P)
        right = str(row.get("right", "") or row.get("option_type", "")).upper()
        if right not in ("P", "C", "PUT", "CALL"):
            continue
        right = "P" if right in ("P", "PUT") else "C"
        
        # Get expiration from row if available
        exp = row.get("expiration") or row.get("exp") or row.get("date") or expiration
        if exp:
            exp = _format_expiration(str(exp))
        
        bid = _extract_float(row, ["bid", "bid_price", "bidPrice"])
        ask = _extract_float(row, ["ask", "ask_price", "askPrice"])
        mid = None
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
        
        exp_date = _parse_date(exp)
        dte = (exp_date - date.today()).days if exp_date else None
        
        contracts.append({
            "symbol": symbol,
            "expiration": exp,
            "strike": strike,
            "right": right,
            "option_type": "PUT" if right == "P" else "CALL",
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "open": _extract_float(row, ["open"]),
            "high": _extract_float(row, ["high"]),
            "low": _extract_float(row, ["low"]),
            "close": _extract_float(row, ["close", "last", "price"]),
            "iv": _extract_float(row, ["implied_vol", "iv", "implied_volatility", "impliedVol"]),
            "delta": _extract_float(row, ["delta"]),
            "gamma": _extract_float(row, ["gamma"]),
            "theta": _extract_float(row, ["theta"]),
            "vega": _extract_float(row, ["vega"]),
            "volume": _extract_int(row, ["volume", "vol"]),
            "open_interest": _extract_int(row, ["open_interest", "oi", "openInterest"]),
            "dte": dte,
        })
    
    return contracts


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
    "snapshot_quote",
    "snapshot_ohlc_bulk",
    "snapshot_quote_bulk",
    # Async versions
    "list_expirations_async",
    "list_strikes_async",
    "snapshot_ohlc_async",
    # High-level chain fetching
    "fetch_chain",
    "fetch_chain_async",
    # ATM filtering
    "_filter_strikes_near_atm",
    # Health check
    "check_theta_health",
    "ThetaHealthStatus",
    # Constants
    "MAX_CONCURRENT_REQUESTS",
]
