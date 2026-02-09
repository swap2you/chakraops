# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS-based Options Chain Provider.

Implements the OptionsChainProvider interface using ORATS live API.
Handles:
- Rate limiting and caching
- Proper DataQuality tracking (MISSING, not fake zeros)
- Concurrent request management
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from app.core.models.data_quality import DataQuality, FieldValue, wrap_field_float, wrap_field_int
from app.core.options.chain_provider import (
    OptionType,
    OptionContract,
    OptionsChain,
    ExpirationInfo,
    ChainProviderResult,
    OptionsChainProvider,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Rate Limiting
# ============================================================================

class RateLimiter:
    """Simple token bucket rate limiter."""
    
    def __init__(self, calls_per_second: float = 5.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = threading.Lock()
    
    def acquire(self) -> None:
        """Wait if needed to respect rate limit."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call = time.time()


# Global rate limiter for ORATS
_ORATS_RATE_LIMITER = RateLimiter(calls_per_second=5.0)


# ============================================================================
# Caching
# ============================================================================

class ChainCache:
    """Thread-safe cache for options chains with TTL."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute default TTL
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[ChainProviderResult, float]] = {}
        self._lock = threading.Lock()
    
    def _make_key(self, symbol: str, expiration: date) -> str:
        return f"{symbol.upper()}_{expiration.isoformat()}"
    
    def get(self, symbol: str, expiration: date) -> Optional[ChainProviderResult]:
        """Get cached result if valid."""
        key = self._make_key(symbol, expiration)
        with self._lock:
            if key in self._cache:
                result, cached_at = self._cache[key]
                if time.time() - cached_at < self.ttl_seconds:
                    return result
                # Expired
                del self._cache[key]
        return None
    
    def set(self, symbol: str, expiration: date, result: ChainProviderResult) -> None:
        """Cache a result."""
        key = self._make_key(symbol, expiration)
        with self._lock:
            self._cache[key] = (result, time.time())
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count removed."""
        now = time.time()
        removed = 0
        with self._lock:
            expired_keys = [
                k for k, (_, cached_at) in self._cache.items()
                if now - cached_at >= self.ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]
                removed += 1
        return removed


# Global cache
_CHAIN_CACHE = ChainCache(ttl_seconds=300)


# ============================================================================
# ORATS Chain Provider
# ============================================================================

class OratsChainProvider:
    """
    ORATS-based implementation of OptionsChainProvider.
    
    Uses ORATS /live/strikes endpoint to fetch chain data.
    """
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[ChainCache] = None,
        use_cache: bool = True,
    ):
        self._rate_limiter = rate_limiter or _ORATS_RATE_LIMITER
        self._cache = cache or _CHAIN_CACHE
        self._use_cache = use_cache
    
    @property
    def name(self) -> str:
        return "ORATS"
    
    def get_expirations(self, symbol: str) -> List[ExpirationInfo]:
        """
        Get available expiration dates for a symbol.
        
        Fetches strikes and extracts unique expirations.
        """
        from app.core.data.orats_client import get_orats_live_strikes, OratsUnavailableError
        
        self._rate_limiter.acquire()
        
        try:
            strikes = get_orats_live_strikes(symbol)
        except OratsUnavailableError as e:
            logger.warning("[ORATS_CHAIN] Failed to get expirations for %s: %s", symbol, e)
            return []
        
        if not strikes:
            return []
        
        # Extract unique expirations
        today = date.today()
        expirations_map: Dict[date, int] = defaultdict(int)
        
        for s in strikes:
            exp_str = s.get("expirDate") or s.get("expirationDate")
            if not exp_str:
                continue
            try:
                exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
                if exp_date > today:
                    expirations_map[exp_date] += 1
            except ValueError:
                continue
        
        # Build ExpirationInfo list
        results = []
        for exp_date, count in sorted(expirations_map.items()):
            dte = (exp_date - today).days
            # Simple heuristic: 3rd Friday = monthly
            is_monthly = exp_date.weekday() == 4 and 15 <= exp_date.day <= 21
            is_weekly = not is_monthly
            
            results.append(ExpirationInfo(
                expiration=exp_date,
                dte=dte,
                is_weekly=is_weekly,
                is_monthly=is_monthly,
                contract_count=count,
            ))
        
        return results
    
    def get_chain(self, symbol: str, expiration: date) -> ChainProviderResult:
        """
        Get options chain for a symbol and expiration.
        """
        # Check cache
        if self._use_cache:
            cached = self._cache.get(symbol, expiration)
            if cached is not None:
                logger.debug("[ORATS_CHAIN] Cache hit for %s %s", symbol, expiration)
                return cached
        
        from app.core.data.orats_client import get_orats_live_strikes, get_orats_live_summaries, OratsUnavailableError
        
        self._rate_limiter.acquire()
        
        start_time = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        
        # Fetch strikes
        try:
            all_strikes = get_orats_live_strikes(symbol)
        except OratsUnavailableError as e:
            result = ChainProviderResult(
                success=False,
                error=f"Failed to fetch strikes: {e}",
                data_quality=DataQuality.ERROR,
            )
            return result
        
        if not all_strikes:
            result = ChainProviderResult(
                success=False,
                error="No strikes data returned",
                data_quality=DataQuality.MISSING,
                missing_fields=["strikes"],
            )
            return result
        
        # Fetch underlying price from summaries
        underlying_price = FieldValue(None, DataQuality.MISSING, "not fetched", "underlying_price")
        try:
            summaries = get_orats_live_summaries(symbol)
            if summaries and len(summaries) > 0:
                price_val = summaries[0].get("stockPrice")
                underlying_price = wrap_field_float(price_val, "underlying_price")
        except OratsUnavailableError:
            pass  # Keep as MISSING
        
        # Filter strikes for this expiration
        exp_str = expiration.isoformat()
        today = date.today()
        dte = (expiration - today).days
        
        filtered_strikes = []
        for s in all_strikes:
            s_exp = s.get("expirDate") or s.get("expirationDate")
            if s_exp == exp_str:
                filtered_strikes.append(s)
        
        if not filtered_strikes:
            result = ChainProviderResult(
                success=False,
                error=f"No strikes found for expiration {exp_str}",
                data_quality=DataQuality.MISSING,
                missing_fields=["strikes_for_expiration"],
            )
            return result
        
        # Convert to OptionContract objects
        contracts = []
        missing_fields_set = set()
        
        for s in filtered_strikes:
            contract = self._parse_strike_to_contract(s, symbol, expiration, dte)
            contract.compute_derived_fields()
            contracts.append(contract)
            
            # Track missing fields
            for field_name in ["bid", "ask", "delta", "open_interest"]:
                fv = getattr(contract, field_name)
                if not fv.is_valid:
                    missing_fields_set.add(field_name)
        
        fetch_duration_ms = int((time.time() - start_time) * 1000)
        
        chain = OptionsChain(
            symbol=symbol.upper(),
            expiration=expiration,
            underlying_price=underlying_price,
            contracts=contracts,
            fetched_at=now_iso,
            source="ORATS",
            fetch_duration_ms=fetch_duration_ms,
        )
        
        # Determine overall data quality
        completeness, missing = chain.compute_data_completeness()
        if completeness >= 0.8:
            data_quality = DataQuality.VALID
        elif completeness >= 0.5:
            data_quality = DataQuality.MISSING  # Partial data
        else:
            data_quality = DataQuality.ERROR  # Too incomplete
        
        result = ChainProviderResult(
            success=True,
            chain=chain,
            data_quality=data_quality,
            missing_fields=list(missing_fields_set),
        )
        
        # Cache the result
        if self._use_cache:
            self._cache.set(symbol, expiration, result)
        
        logger.info(
            "[ORATS_CHAIN] Fetched %s %s: %d contracts, completeness=%.1f%%, %dms",
            symbol, exp_str, len(contracts), completeness * 100, fetch_duration_ms
        )
        
        return result
    
    def get_chains_batch(
        self,
        symbol: str,
        expirations: List[date],
        max_concurrent: int = 3,
    ) -> Dict[date, ChainProviderResult]:
        """
        Get multiple chains for a symbol (batch operation).
        
        Uses thread pool for concurrent fetching with bounds.
        """
        results: Dict[date, ChainProviderResult] = {}
        
        # First, check cache for all
        uncached_expirations = []
        for exp in expirations:
            if self._use_cache:
                cached = self._cache.get(symbol, exp)
                if cached is not None:
                    results[exp] = cached
                    continue
            uncached_expirations.append(exp)
        
        if not uncached_expirations:
            return results
        
        # Fetch uncached in parallel (bounded)
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(uncached_expirations))) as executor:
            future_to_exp = {
                executor.submit(self.get_chain, symbol, exp): exp
                for exp in uncached_expirations
            }
            
            for future in as_completed(future_to_exp):
                exp = future_to_exp[future]
                try:
                    result = future.result()
                    results[exp] = result
                except Exception as e:
                    logger.exception("[ORATS_CHAIN] Error fetching chain for %s %s: %s", symbol, exp, e)
                    results[exp] = ChainProviderResult(
                        success=False,
                        error=str(e),
                        data_quality=DataQuality.ERROR,
                    )
        
        return results
    
    def _parse_strike_to_contract(
        self,
        strike_data: Dict[str, Any],
        symbol: str,
        expiration: date,
        dte: int,
    ) -> OptionContract:
        """
        Parse ORATS strike data to OptionContract.
        
        IMPORTANT: Use proper DataQuality tracking, not fake zeros.
        """
        # Determine option type
        put_call = strike_data.get("putCall", "") or strike_data.get("callPut", "")
        if put_call.upper() in ("P", "PUT"):
            option_type = OptionType.PUT
        else:
            option_type = OptionType.CALL
        
        # Extract strike price
        strike = float(strike_data.get("strike", 0))
        
        # Wrap all fields with proper data quality tracking
        bid = wrap_field_float(strike_data.get("bid"), "bid")
        ask = wrap_field_float(strike_data.get("ask"), "ask")
        last = wrap_field_float(strike_data.get("last"), "last")
        
        # Mid - may be provided or computed
        mid_raw = strike_data.get("mid")
        if mid_raw is not None:
            mid = wrap_field_float(mid_raw, "mid")
        else:
            # Will be computed from bid/ask later
            mid = FieldValue(None, DataQuality.MISSING, "not provided, will compute", "mid")
        
        # Liquidity fields
        open_interest = wrap_field_int(strike_data.get("openInt") or strike_data.get("openInterest"), "open_interest")
        volume = wrap_field_int(strike_data.get("volume"), "volume")
        
        # Greeks - ORATS may or may not provide all
        delta = wrap_field_float(strike_data.get("delta"), "delta")
        gamma = wrap_field_float(strike_data.get("gamma"), "gamma")
        theta = wrap_field_float(strike_data.get("theta"), "theta")
        vega = wrap_field_float(strike_data.get("vega"), "vega")
        
        # Implied volatility - ORATS has various IV fields
        iv_raw = strike_data.get("iv") or strike_data.get("impliedVol") or strike_data.get("smvVol")
        iv = wrap_field_float(iv_raw, "iv")
        
        now_iso = datetime.now(timezone.utc).isoformat()
        
        return OptionContract(
            symbol=symbol.upper(),
            expiration=expiration,
            strike=strike,
            option_type=option_type,
            bid=bid,
            ask=ask,
            mid=mid,
            last=last,
            open_interest=open_interest,
            volume=volume,
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            iv=iv,
            dte=dte,
            fetched_at=now_iso,
            source="ORATS",
        )


# ============================================================================
# Factory Function
# ============================================================================

def get_chain_provider() -> OratsChainProvider:
    """Get the default chain provider instance."""
    return OratsChainProvider()


__all__ = [
    "OratsChainProvider",
    "RateLimiter",
    "ChainCache",
    "get_chain_provider",
]
