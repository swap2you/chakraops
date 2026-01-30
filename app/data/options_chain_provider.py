# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider using Theta v3 pipeline.

Implements the OptionsChainProvider interface for the signal engine
using the new theta_v3_pipeline module.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Timeout for provider calls
CHAIN_REQUEST_TIMEOUT = 30.0

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
    """Theta v3 provider using the basic pipeline pattern.
    
    Uses theta_v3_pipeline functions:
    - list_expirations() for get_expirations()
    - list_strikes() + snapshot_ohlc() for get_chain()
    
    Includes strike limiting to focus on near-ATM options for efficiency.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
        strike_limit: int = 30,
    ) -> None:
        from app.core.settings import get_theta_base_url
        
        self.base_url = (base_url or get_theta_base_url()).rstrip("/")
        self.timeout = timeout
        self.strike_limit = strike_limit  # Max strikes per expiration (centered on ATM)
        # Cache expirations to avoid redundant API calls
        self._expiration_cache: Dict[str, List[str]] = {}

    def get_expirations(self, symbol: str) -> List[date]:
        """Get expirations via theta_v3_pipeline.list_expirations."""
        from app.data.theta_v3_pipeline import list_expirations
        
        symbol = (symbol or "").upper()
        if not symbol:
            return []
        
        # Check cache
        if symbol in self._expiration_cache:
            exp_strings = self._expiration_cache[symbol]
        else:
            try:
                exp_strings = list_expirations(
                    symbol,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
                self._expiration_cache[symbol] = exp_strings
            except Exception as e:
                logger.debug("[OptionsChain] get_expirations failed for %s: %s", symbol, e)
                return []
        
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

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Get chain for specific expiration using pipeline.
        
        Steps:
        1. list_strikes(symbol, expiration)
        2. Filter strikes to near-ATM (strike_limit)
        3. For each strike: snapshot_ohlc(symbol, expiration, strike, right)
        """
        from app.data.theta_v3_pipeline import list_strikes, snapshot_ohlc, _filter_strikes_near_atm
        
        symbol = (symbol or "").upper()
        right_upper = (right or "P").upper()
        if right_upper not in ("P", "C"):
            right_upper = "P"
        
        # Format expiration as YYYY-MM-DD
        exp_str = expiry.strftime("%Y-%m-%d")
        
        try:
            # Get all strikes for this expiration
            all_strikes = list_strikes(
                symbol,
                exp_str,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            
            if not all_strikes:
                logger.debug("[OptionsChain] No strikes for %s %s", symbol, exp_str)
                return []
            
            # Filter to near-ATM strikes for efficiency
            strikes = _filter_strikes_near_atm(all_strikes, None, self.strike_limit)
            logger.debug("[OptionsChain] %s %s: %d strikes (filtered from %d)", 
                        symbol, exp_str, len(strikes), len(all_strikes))
            
            # Fetch OHLC for each strike
            out: List[Dict[str, Any]] = []
            for strike in strikes:
                contract = snapshot_ohlc(
                    symbol,
                    exp_str,
                    strike,
                    right_upper,
                    base_url=self.base_url,
                    timeout=self.timeout,
                )
                
                if contract:
                    # Normalize output format for signal engine
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
                        "dte": contract.get("dte"),
                    })
            
            logger.debug("[OptionsChain] %s %s %s returned %d contracts", 
                        symbol, exp_str, right_upper, len(out))
            return out
            
        except Exception as e:
            logger.debug("[OptionsChain] get_chain failed for %s %s %s: %s", 
                        symbol, expiry, right, e)
            return []

    def get_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> Dict[str, Any]:
        """Get full chain with DTE filtering using pipeline."""
        from app.data.theta_v3_pipeline import fetch_chain
        
        try:
            contracts = fetch_chain(
                symbol,
                dte_min=dte_min,
                dte_max=dte_max,
                strike_limit=self.strike_limit,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            
            if not contracts:
                return {
                    "symbol": symbol,
                    "contracts": [],
                    "puts": [],
                    "calls": [],
                    "expiration_count": 0,
                    "contract_count": 0,
                    "chain_status": "empty_chain",
                    "data_source": "live",
                    "error": "No contracts returned",
                }
            
            # Split into puts and calls
            puts = [c for c in contracts if c.get("right") == "P"]
            calls = [c for c in contracts if c.get("right") == "C"]
            expirations = sorted(set(c.get("expiration", "") for c in contracts if c.get("expiration")))
            
            return {
                "symbol": symbol,
                "expirations": expirations,
                "contracts": contracts,
                "puts": puts,
                "calls": calls,
                "expiration_count": len(expirations),
                "contract_count": len(contracts),
                "chain_status": "ok",
                "data_source": "live",
            }
            
        except Exception as e:
            return {
                "symbol": symbol,
                "chain_status": "no_options_for_symbol",
                "error": str(e),
            }

    def clear_cache(self) -> None:
        """Clear expiration cache."""
        self._expiration_cache.clear()


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
