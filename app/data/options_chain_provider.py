# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider using Theta v3 per-expiration calls.

Correct approach:
1. Call list_expirations(symbol) to get available expirations
2. For each expiration needed, call snapshot_ohlc(symbol, expiration)
3. DO NOT pass expiration="*" - Theta API rejects it
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
    """Theta v3 provider using per-expiration snapshot_ohlc calls."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
    ) -> None:
        from app.core.settings import get_theta_base_url

        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout
        self._provider = None

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

    def get_expirations(self, symbol: str) -> List[date]:
        """Get expirations via ThetaV3Provider.list_expirations."""
        try:
            provider = self._get_provider()
            exp_strings = provider.list_expirations(symbol)
            
            if not exp_strings:
                logger.debug("[OptionsChain] No expirations for %s", symbol)
                return []
            
            # Convert strings to dates
            out: List[date] = []
            for exp_str in exp_strings:
                d = _parse_date_any(exp_str)
                if d:
                    out.append(d)
            
            return sorted(out)
            
        except Exception as e:
            logger.debug("[OptionsChain] get_expirations failed for %s: %s", symbol, e)
            return []

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Get chain for specific expiration via snapshot_ohlc."""
        try:
            provider = self._get_provider()
            symbol_upper = symbol.upper()
            right_upper = (right or "P").upper()
            
            # Format expiration as YYYY-MM-DD
            exp_str = expiry.strftime("%Y-%m-%d")
            
            # Call snapshot_ohlc for this specific expiration
            contracts = provider.snapshot_ohlc(symbol_upper, exp_str)
            
            if not contracts:
                return []
            
            # Filter by right and normalize output
            out: List[Dict[str, Any]] = []
            for contract in contracts:
                contract_right = contract.get("right", "").upper()
                if contract_right != right_upper:
                    continue
                
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
