# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider abstraction (Phase 5). Uses efficient Theta v3 bulk endpoints."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for all provider calls
CHAIN_REQUEST_TIMEOUT = 10.0

# Fallback weekly expirations: OFF by default
OPTIONS_FALLBACK_WEEKLY_ENV = "OPTIONS_FALLBACK_WEEKLY_EXPIRATIONS"
OPTIONS_FALLBACK_DAYS_ENV = "OPTIONS_FALLBACK_DAYS"
DEFAULT_FALLBACK_DAYS = 14


class OptionsChainProvider(ABC):
    """Interface for options expirations and chain data. Implementations must fail fast."""

    @abstractmethod
    def get_expirations(self, symbol: str) -> List[date]:
        """Return expiration dates for symbol. Empty list on failure -> chain_unavailable."""
        ...

    @abstractmethod
    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Return list of contract records for symbol/expiry/right.

        Each record must have: strike, bid, ask, delta, iv (or None).
        Optional: volume, open_interest. Empty list on failure.
        """
        ...


class ThetaDataOptionsChainProvider(OptionsChainProvider):
    """Theta REST (localhost:25503/v3) using efficient bulk snapshot endpoints.
    
    Uses snapshot_ohlc or snapshot_quote to fetch all contracts for an expiration
    in a single call, instead of querying each strike individually.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
    ) -> None:
        from app.core.settings import get_theta_base_url

        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout
        self._provider = None  # Lazy-loaded ThetaV3Provider

    def _get_provider(self):
        """Lazy load ThetaV3Provider."""
        if self._provider is None:
            from app.data.theta_v3_provider import ThetaV3Provider
            self._provider = ThetaV3Provider(
                base_url=self.base_url,
                timeout=self.timeout,
                fallback_enabled=False,  # Don't use fallback in chain provider
            )
        return self._provider

    def get_expirations(self, symbol: str) -> List[date]:
        """Fetch expirations using ThetaV3Provider.list_expirations."""
        try:
            provider = self._get_provider()
            exp_strings = provider.list_expirations(symbol)
            
            if not exp_strings:
                logger.debug("[OptionsChain] get_expirations empty for %s", symbol)
                return []
            
            out: List[date] = []
            for exp_str in exp_strings:
                d = _parse_date_any(exp_str)
                if d is not None:
                    out.append(d)
            
            out.sort()
            return out
        except Exception as e:
            logger.debug("[OptionsChain] get_expirations failed for %s: %s", symbol, e)
            return []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Fetch chain using efficient bulk snapshot endpoint.
        
        Uses snapshot_ohlc to get all contracts for an expiration in a single call,
        then filters by right (PUT/CALL).
        """
        try:
            provider = self._get_provider()
            symbol_upper = (symbol or "").upper()
            exp_str = expiry.strftime("%Y-%m-%d")
            right_upper = (right or "P").upper()
            
            # Fetch all contracts for this expiration in one call
            contracts = provider.snapshot_ohlc(symbol_upper, exp_str)
            
            # Fall back to snapshot_quote if snapshot_ohlc returns empty
            if not contracts:
                contracts = provider.snapshot_quote(symbol_upper, exp_str)
            
            if not contracts:
                logger.debug("[OptionsChain] get_chain no contracts for %s %s", symbol_upper, exp_str)
                return []
            
            # Filter by right and normalize to expected format
            out: List[Dict[str, Any]] = []
            for contract in contracts:
                contract_right = contract.get("right", "").upper()
                
                # Map option_type if right not present
                if not contract_right:
                    opt_type = contract.get("option_type", "").upper()
                    if opt_type in ("PUT", "P"):
                        contract_right = "P"
                    elif opt_type in ("CALL", "C"):
                        contract_right = "C"
                
                # Skip if doesn't match requested right
                if contract_right != right_upper:
                    continue
                
                # Normalize to expected format
                out.append({
                    "strike": contract.get("strike"),
                    "bid": contract.get("bid"),
                    "ask": contract.get("ask"),
                    "delta": contract.get("delta"),
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
        dte_min: int = 30,
        dte_max: int = 45,
    ) -> Dict[str, Any]:
        """Fetch full chain for a symbol within DTE window.
        
        Returns dict with 'contracts', 'puts', 'calls', 'chain_status', etc.
        This is a convenience method that wraps ThetaV3Provider.fetch_full_chain.
        """
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
    """Return next weekly (Friday) expirations within the given number of days from today."""
    today = date.today()
    out: List[date] = []
    d = today
    for _ in range(days):
        if d.weekday() == 4:  # Friday
            out.append(d)
        d += timedelta(days=1)
        if (d - today).days > days:
            break
    return sorted(out)[:4]  # Cap at 4 expirations


class FallbackWeeklyExpirationsProvider(OptionsChainProvider):
    """Wrapper that when inner returns zero expirations, optionally returns nearest weekly expirations.

    OFF by default. Set OPTIONS_FALLBACK_WEEKLY_EXPIRATIONS=1 to enable.
    OPTIONS_FALLBACK_DAYS (default 14) limits how many days ahead to look.
    """

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
                logger.info(
                    "[OptionsChain] Fallback: using %d weekly expiration(s) for %s",
                    len(fallback), symbol,
                )
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
    if len(s) >= 8 and s.replace("-", "").isdigit():
        clean = s.replace("-", "")
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

# Theta v3 endpoints used (via ThetaV3Provider):
# - GET /v3/option/list/expirations?symbol=SYMBOL&format=json
# - GET /v3/option/snapshot/ohlc?symbol=SYMBOL&expiration=YYYYMMDD&format=json (bulk fetch)
# - GET /v3/option/snapshot/quote?symbol=SYMBOL&expiration=YYYYMMDD&format=json (fallback)
