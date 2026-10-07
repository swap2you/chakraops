# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider. ORATS Live Data is the default (token from ORATS_API_TOKEN)."""

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

    def get_option_context(self, symbol: str) -> Optional[Any]:
        """Return OptionContext for symbol (expected move, IV rank, term structure, etc.). Optional; return None if not supported."""
        return None

    @abstractmethod
    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        """Return contracts for symbol/expiry/right."""
        ...


class OratsOptionsChainProvider(OptionsChainProvider):
    """ORATS Live Data provider. Token from ORATS_API_TOKEN only."""

    def __init__(self, timeout: float = CHAIN_REQUEST_TIMEOUT) -> None:
        from app.core.options.providers.orats_provider import OratsOptionsChainProvider as _OratsImpl
        self._impl = _OratsImpl(timeout=timeout)

    def get_expirations(self, symbol: str) -> List[date]:
        return self._impl.get_expirations(symbol)

    def get_chain(
        self,
        symbol: str,
        expiry: date,
        right: str,
    ) -> List[Dict[str, Any]]:
        return self._impl.get_chain(symbol, expiry, right)

    def get_option_context(self, symbol: str) -> Optional[Any]:
        return self._impl.get_option_context(symbol)

    def get_full_chain(
        self,
        symbol: str,
        dte_min: int = 7,
        dte_max: int = 45,
    ) -> Dict[str, Any]:
        return self._impl.get_full_chain(symbol, dte_min=dte_min, dte_max=dte_max)

    def clear_cache(self) -> None:
        self._impl.clear_cache()


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

    def get_option_context(self, symbol: str) -> Optional[Any]:
        return getattr(self._inner, "get_option_context", lambda s: None)(symbol)


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
    "OratsOptionsChainProvider",
    "FallbackWeeklyExpirationsProvider",
    "CHAIN_REQUEST_TIMEOUT",
]
