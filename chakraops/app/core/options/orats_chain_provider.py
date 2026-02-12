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


def normalize_put_call(raw: Any) -> Optional[OptionType]:
    """
    Normalize raw put/call string to OptionType. Handles case and common variants.
    - PUT: "P", "PUT", "PUTS"
    - CALL: "C", "CALL", "CALLS"
    - else: None
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if s in ("P", "PUT", "PUTS"):
        return OptionType.PUT
    if s in ("C", "CALL", "CALLS"):
        return OptionType.CALL
    return None


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

def _resolve_chain_source(override: Optional[str]) -> str:
    """Single routing rule: OPEN → LIVE, else → DELAYED. Used everywhere."""
    if override is not None and override in ("LIVE", "DELAYED"):
        return override
    try:
        from app.market.market_hours import get_chain_source
        return get_chain_source()
    except Exception:
        return "DELAYED"


class OratsChainProvider:
    """
    ORATS-based implementation of OptionsChainProvider.
    
    Chain source: LIVE when market OPEN (/datav2/live/…); DELAYED otherwise
    (/datav2/strikes + /datav2/strikes/options with full enrichment).
    """
    
    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        cache: Optional[ChainCache] = None,
        use_cache: bool = True,
        chain_source: Optional[str] = None,
    ):
        self._rate_limiter = rate_limiter or _ORATS_RATE_LIMITER
        self._cache = cache or _CHAIN_CACHE
        self._use_cache = use_cache
        self._chain_source = _resolve_chain_source(chain_source)
    
    @property
    def name(self) -> str:
        return "ORATS"
    
    def get_expirations(self, symbol: str) -> List[ExpirationInfo]:
        """
        Get available expiration dates for a symbol.
        LIVE: /datav2/live/strikes. DELAYED: /datav2/strikes (pipeline).
        """
        if self._chain_source == "DELAYED":
            return self._get_expirations_delayed(symbol)
        return self._get_expirations_live(symbol)
    
    def _get_expirations_delayed(self, symbol: str) -> List[ExpirationInfo]:
        """Expirations from pipeline /datav2/strikes (DELAYED)."""
        from app.core.config.wheel_strategy_config import WHEEL_CONFIG, DTE_MIN, DTE_MAX
        from app.core.options.orats_chain_pipeline import fetch_base_chain
        dte_min = WHEEL_CONFIG.get(DTE_MIN, 30)
        dte_max = WHEEL_CONFIG.get(DTE_MAX, 45)
        self._rate_limiter.acquire()
        try:
            base_contracts, _, err, _ = fetch_base_chain(
                symbol, dte_min=dte_min, dte_max=dte_max, chain_mode="DELAYED"
            )
        except Exception as e:
            logger.warning("[ORATS_CHAIN] DELAYED expirations failed for %s: %s", symbol, e)
            return []
        if err or not base_contracts:
            return []
        today = date.today()
        expirations_map: Dict[date, int] = defaultdict(int)
        for c in base_contracts:
            if getattr(c, "expiration", None):
                expirations_map[c.expiration] += 1
        results = []
        for exp_date, count in sorted(expirations_map.items()):
            dte = (exp_date - today).days
            is_monthly = exp_date.weekday() == 4 and 15 <= exp_date.day <= 21
            results.append(ExpirationInfo(
                expiration=exp_date,
                dte=dte,
                is_weekly=not is_monthly,
                is_monthly=is_monthly,
                contract_count=count,
            ))
        return results
    
    def _get_expirations_live(self, symbol: str) -> List[ExpirationInfo]:
        """Expirations from /datav2/live/strikes (LIVE)."""
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
        LIVE: /datav2/live/strikes + summaries. DELAYED: pipeline with /datav2/strikes + /datav2/strikes/options.
        """
        # Check cache
        if self._use_cache:
            cached = self._cache.get(symbol, expiration)
            if cached is not None:
                logger.debug("[ORATS_CHAIN] Cache hit for %s %s", symbol, expiration)
                return cached
        if self._chain_source == "DELAYED":
            batch = self.get_chains_batch(symbol, [expiration], max_concurrent=1)
            return batch.get(expiration, ChainProviderResult(
                success=False,
                error="No chain for expiration",
                data_quality=DataQuality.MISSING,
            ))
        return self._get_chain_live(symbol, expiration)
    
    def _get_chain_live(self, symbol: str, expiration: date) -> ChainProviderResult:
        """Single chain from /datav2/live/strikes + summaries (LIVE)."""
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
        delta_lo: Optional[float] = None,
        delta_hi: Optional[float] = None,
    ) -> Dict[date, ChainProviderResult]:
        """
        Get multiple chains for a symbol (batch operation).
        DELAYED: one fetch_option_chain (strikes + strikes/options) then split by expiration.
        LIVE: concurrent get_chain per expiration.
        """
        if self._chain_source == "DELAYED":
            return self._get_chains_batch_delayed(symbol, expirations, delta_lo=delta_lo, delta_hi=delta_hi)
        results: Dict[date, ChainProviderResult] = {}
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
        with ThreadPoolExecutor(max_workers=min(max_concurrent, len(uncached_expirations))) as executor:
            future_to_exp = {
                executor.submit(self._get_chain_live, symbol, exp): exp
                for exp in uncached_expirations
            }
            for future in as_completed(future_to_exp):
                exp = future_to_exp[future]
                try:
                    result = future.result()
                    results[exp] = result
                    if self._use_cache and result.success:
                        self._cache.set(symbol, exp, result)
                except Exception as e:
                    logger.exception("[ORATS_CHAIN] Error fetching chain for %s %s: %s", symbol, exp, e)
                    results[exp] = ChainProviderResult(
                        success=False,
                        error=str(e),
                        data_quality=DataQuality.ERROR,
                    )
        return results
    
    def _get_chains_batch_delayed(
        self, symbol: str, expirations: List[date],
        delta_lo: Optional[float] = None,
        delta_hi: Optional[float] = None,
    ) -> Dict[date, ChainProviderResult]:
        """One pipeline call (strikes + strikes/options) then split by expiration."""
        from app.core.config.wheel_strategy_config import WHEEL_CONFIG, DTE_MIN, DTE_MAX
        from app.core.options.orats_chain_pipeline import fetch_option_chain
        dte_min = WHEEL_CONFIG.get(DTE_MIN, 30)
        dte_max = WHEEL_CONFIG.get(DTE_MAX, 45)
        self._rate_limiter.acquire()
        try:
            chain_result = fetch_option_chain(
                symbol, dte_min=dte_min, dte_max=dte_max, chain_mode="DELAYED",
                delta_lo=delta_lo, delta_hi=delta_hi,
            )
        except Exception as e:
            logger.warning("[ORATS_CHAIN] DELAYED pipeline failed for %s: %s", symbol, e)
            return {exp: ChainProviderResult(success=False, error=str(e), data_quality=DataQuality.ERROR) for exp in expirations}
        if chain_result.error or not chain_result.contracts:
            err = chain_result.error or "No contracts"
            return {exp: ChainProviderResult(success=False, error=err, data_quality=DataQuality.MISSING) for exp in expirations}
        exp_set = set(expirations)
        by_exp: Dict[date, List[Any]] = defaultdict(list)
        for c in chain_result.contracts:
            exp = getattr(c, "expiration", None)
            if exp and exp in exp_set:
                by_exp[exp].append(c)
        results = {}
        for exp in expirations:
            contracts_list = by_exp.get(exp, [])
            if not contracts_list:
                results[exp] = ChainProviderResult(
                    success=False,
                    error=f"No contracts for {exp}",
                    data_quality=DataQuality.MISSING,
                )
                continue
            telemetry = getattr(chain_result, "strikes_options_telemetry", None) if chain_result else None
            stage2_trace = getattr(chain_result, "stage2_trace", None) if chain_result else None
            option_contracts = [self._enriched_to_option_contract(ec, symbol) for ec in contracts_list]
            for oc in option_contracts:
                oc.compute_derived_fields()
            underlying = chain_result.underlying_price
            uv = wrap_field_float(underlying, "underlying_price") if underlying is not None else FieldValue(None, DataQuality.MISSING, "", "underlying_price")
            chain = OptionsChain(
                symbol=symbol.upper(),
                expiration=exp,
                underlying_price=uv,
                contracts=option_contracts,
                fetched_at=chain_result.fetched_at or datetime.now(timezone.utc).isoformat(),
                source="ORATS",
                fetch_duration_ms=chain_result.fetch_duration_ms or 0,
            )
            completeness, missing = chain.compute_data_completeness()
            dq = DataQuality.VALID if completeness >= 0.8 else (DataQuality.MISSING if completeness >= 0.5 else DataQuality.ERROR)
            results[exp] = ChainProviderResult(
                success=True,
                chain=chain,
                data_quality=dq,
                missing_fields=list(missing),
                telemetry=telemetry,
                stage2_trace=stage2_trace,
            )
            if self._use_cache:
                self._cache.set(symbol, exp, results[exp])
            telemetry = None  # Attach only to first expiration result
        return results
    
    def _enriched_to_option_contract(self, ec: Any, symbol: str) -> OptionContract:
        """Convert pipeline EnrichedContract to chain_provider OptionContract. Read option type from ALL known keys; never default to CALL."""
        OPTION_TYPE_KEYS = ("optionType", "option_type", "putCall", "callPut", "put_call", "call_put")
        raw = None
        for key in OPTION_TYPE_KEYS:
            v = getattr(ec, key, None) if hasattr(ec, key) else (ec.get(key) if isinstance(ec, dict) else None)
            if v is not None and str(v).strip():
                raw = v
                break
        if raw is None:
            raw = getattr(ec, "option_type", None)
        option_type = normalize_put_call(raw) or OptionType.UNKNOWN
        return OptionContract(
            symbol=symbol.upper(),
            expiration=ec.expiration,
            strike=float(getattr(ec, "strike", 0)),
            option_type=option_type,
            option_symbol=getattr(ec, "opra_symbol", None),
            bid=wrap_field_float(getattr(ec, "bid", None), "bid"),
            ask=wrap_field_float(getattr(ec, "ask", None), "ask"),
            mid=wrap_field_float(getattr(ec, "mid", None), "mid"),
            last=FieldValue(None, DataQuality.MISSING, "", "last"),
            open_interest=wrap_field_int(getattr(ec, "open_interest", None), "open_interest"),
            volume=wrap_field_int(getattr(ec, "volume", None), "volume"),
            delta=wrap_field_float(getattr(ec, "delta", None), "delta"),
            gamma=wrap_field_float(getattr(ec, "gamma", None), "gamma"),
            theta=wrap_field_float(getattr(ec, "theta", None), "theta"),
            vega=wrap_field_float(getattr(ec, "vega", None), "vega"),
            iv=wrap_field_float(getattr(ec, "iv", None), "iv"),
            dte=int(getattr(ec, "dte", 0)),
            fetched_at=getattr(ec, "fetched_at", None),
            source="ORATS",
        )
    
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
        # Determine option type (normalize put/call variants)
        put_call = strike_data.get("putCall") or strike_data.get("callPut")
        option_type = normalize_put_call(put_call) or OptionType.CALL
        
        # Extract strike price
        strike = float(strike_data.get("strike", 0))
        
        # Wrap all fields with proper data quality tracking; map ORATS key variants
        bid = wrap_field_float(strike_data.get("bid") or strike_data.get("bidPrice"), "bid")
        ask = wrap_field_float(strike_data.get("ask") or strike_data.get("askPrice"), "ask")
        last = wrap_field_float(strike_data.get("last"), "last")
        
        # Mid - may be provided or computed
        mid_raw = strike_data.get("mid")
        if mid_raw is not None:
            mid = wrap_field_float(mid_raw, "mid")
        else:
            # Will be computed from bid/ask later
            mid = FieldValue(None, DataQuality.MISSING, "not provided, will compute", "mid")
        
        # Liquidity fields: openInterest, open_interest, oi -> canonical open_interest
        open_interest = wrap_field_int(
            strike_data.get("openInt") or strike_data.get("openInterest") or strike_data.get("open_interest") or strike_data.get("oi"),
            "open_interest",
        )
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

def get_chain_provider(chain_source: Optional[str] = None) -> OratsChainProvider:
    """Get the default chain provider instance. chain_source: LIVE | DELAYED (default from get_chain_source())."""
    return OratsChainProvider(chain_source=chain_source)


__all__ = [
    "OratsChainProvider",
    "RateLimiter",
    "ChainCache",
    "get_chain_provider",
    "normalize_put_call",
]
