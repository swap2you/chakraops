# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider using Theta v3 snapshot_ohlc for complete chains.

Key change: Uses snapshot_ohlc(symbol, '*') to get ALL contracts in ONE call.
No more per-strike or per-expiration fetching.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for provider calls
CHAIN_REQUEST_TIMEOUT = 15.0

# Fallback weekly expirations: OFF by default
OPTIONS_FALLBACK_WEEKLY_ENV = "OPTIONS_FALLBACK_WEEKLY_EXPIRATIONS"
OPTIONS_FALLBACK_DAYS_ENV = "OPTIONS_FALLBACK_DAYS"
DEFAULT_FALLBACK_DAYS = 14


class OptionsChainProvider(ABC):
    """Interface for options chain data."""

    @abstractmethod
    def get_expirations(self, symbol: str) -> List[date]:
        """Return expiration dates for symbol."""
        ...

    @abstractmethod
    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Return contracts for symbol/expiry/right."""
        ...


class ThetaDataOptionsChainProvider(OptionsChainProvider):
    """Theta v3 provider using snapshot_ohlc for complete chain retrieval.
    
    Uses snapshot_ohlc(symbol, '*') to get ALL contracts in ONE call,
    then filters by expiration and right as needed.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
    ) -> None:
        from app.core.settings import get_theta_base_url

        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout
        self._provider = None
        self._chain_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_time: Dict[str, datetime] = {}
        self._cache_ttl = timedelta(seconds=30)  # Cache for 30 seconds

    def _get_provider(self):
        """Lazy load ThetaV3Provider."""
        if self._provider is None:
            from app.data.theta_v3_provider import ThetaV3Provider
            self._provider = ThetaV3Provider(
                base_url=self.base_url,
                timeout=self.timeout,
                fallback_enabled=False,
            )
        return self._provider

    def _get_full_chain(self, symbol: str) -> List[Dict[str, Any]]:
        """Get full chain for symbol, using cache if fresh."""
        symbol = symbol.upper()
        now = datetime.now()
        
        # Check cache
        if symbol in self._chain_cache:
            cache_age = now - self._cache_time.get(symbol, datetime.min)
            if cache_age < self._cache_ttl:
                return self._chain_cache[symbol]
        
        # Fetch fresh data using snapshot_ohlc with '*' for all expirations
        provider = self._get_provider()
        contracts = provider.snapshot_ohlc(symbol, "*")
        
        # Update cache
        self._chain_cache[symbol] = contracts
        self._cache_time[symbol] = now
        
        return contracts

    def get_expirations(self, symbol: str) -> List[date]:
        """Get expirations from the full chain."""
        try:
            contracts = self._get_full_chain(symbol)
            
            if not contracts:
                logger.debug("[OptionsChain] No contracts for %s", symbol)
                return []
            
            # Extract unique expirations
            expirations_set: set = set()
            for contract in contracts:
                exp_str = contract.get("expiration", "")
                if exp_str:
                    d = _parse_date_any(exp_str)
                    if d:
                        expirations_set.add(d)
            
            return sorted(expirations_set)
            
        except Exception as e:
            logger.debug("[OptionsChain] get_expirations failed for %s: %s", symbol, e)
            return []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Get chain filtered by expiration and right from the full chain."""
        try:
            contracts = self._get_full_chain(symbol)
            
            if not contracts:
                return []
            
            symbol_upper = symbol.upper()
            right_upper = (right or "P").upper()
            expiry_str = expiry.strftime("%Y-%m-%d")
            
            # Filter contracts
            out: List[Dict[str, Any]] = []
            for contract in contracts:
                # Filter by right
                contract_right = contract.get("right", "").upper()
                if contract_right != right_upper:
                    continue
                
                # Filter by expiration
                contract_exp = contract.get("expiration", "")
                if not contract_exp:
                    continue
                
                # Normalize and compare expiration
                contract_exp_normalized = contract_exp.replace("-", "")[:8]
                expiry_normalized = expiry_str.replace("-", "")[:8]
                if contract_exp_normalized != expiry_normalized:
                    continue
                
                # Normalize output format
                out.append({
                    "strike": contract.get("strike"),
                    "bid": contract.get("bid"),
                    "ask": contract.get("ask"),
                    "mid": contract.get("mid"),
                    "delta": contract.get("delta"),
                    "gamma": contract.get("gamma"),
                    "theta": contract.get("theta"),
                    "vega": contract.get("vega"),
                    "iv": contract.get("iv"),
                    "open_interest": contract.get("open_interest"),
                    "volume": contract.get("volume"),
                    "right": right_upper,
                    "expiry": expiry.isoformat(),
                })
            
            return out
            
        except Exception as e:
            logger.debug("[OptionsChain] get_chain failed for %s %s %s: %s", symbol, expiry, right, e)
            return []

    def get_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> Dict[str, Any]:
        """Get full chain with DTE filtering via ThetaV3Provider."""
        try:
            provider = self._get_provider()
            result = provider.fetch_full_chain(symbol, dte_min=dte_min, dte_max=dte_max)
            
            return {
                "symbol": result.symbol,
                "expirations": result.expirations,
                "contracts": result.contracts,
                "puts": result.puts,
                "calls": result.calls,
                "expiration_count": result.expiration_count,
                "contract_count": result.contract_count,
                "chain_status": result.chain_status,
                "data_source": result.data_source,
                "error": result.error,
            }
        except Exception as e:
            return {
                "symbol": symbol,
                "chain_status": "no_options_for_symbol",
                "error": str(e),
            }


def _next_weekly_expirations_within_days(days: int) -> List[date]:
    """Return next weekly (Friday) expirations within N days."""
    today = date.today()
    out: List[date] = []
    d = today
    for _ in range(days):
        if d.weekday() == 4:  # Friday
            out.append(d)
        d += timedelta(days=1)
        if (d - today).days > days:
            break
    return sorted(out)[:4]


class FallbackWeeklyExpirationsProvider(OptionsChainProvider):
    """Wrapper that falls back to weekly expirations if inner returns none."""

    def __init__(self, inner: OptionsChainProvider) -> None:
        self._inner = inner
        self._enabled = os.getenv(OPTIONS_FALLBACK_WEEKLY_ENV, "").strip().lower() in ("1", "true", "yes")
        try:
            self._days = int(os.getenv(OPTIONS_FALLBACK_DAYS_ENV, str(DEFAULT_FALLBACK_DAYS)))
        except ValueError:
            self._days = DEFAULT_FALLBACK_DAYS

    def get_expirations(self, symbol: str) -> List[date]:
        result = self._inner.get_expirations(symbol)
        if result:
            return result
        if self._enabled and self._days > 0:
            fallback = _next_weekly_expirations_within_days(self._days)
            if fallback:
                logger.info("[OptionsChain] Using %d weekly fallback expiration(s) for %s", len(fallback), symbol)
                return fallback
        return []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        return self._inner.get_chain(symbol, expiry, right)


def _parse_date_any(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    s = str(x).strip()
    if len(s) >= 8 and s.replace("-", "").replace("/", "")[:8].isdigit():
        clean = s.replace("-", "").replace("/", "")[:8]
        try:
            return date(int(clean[:4]), int(clean[4:6]), int(clean[6:8]))
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s).date()
    except (ValueError, TypeError):
        pass
    return None


__all__ = [
    "OptionsChainProvider",
    "ThetaDataOptionsChainProvider",
    "FallbackWeeklyExpirationsProvider",
    "CHAIN_REQUEST_TIMEOUT",
]
