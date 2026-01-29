# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Options chain provider abstraction (Phase 5). Fail fast, short timeouts, no retries."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.data.theta_v3_routes import option_url, build_headers

logger = logging.getLogger(__name__)

# Timeout for all provider calls; retries=0 by default
CHAIN_REQUEST_TIMEOUT = 5.0

# Fallback weekly expirations: OFF by default (Phase 8)
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
        Optional: volume, open_interest (or oi). Empty list on failure.
        """
        ...


class ThetaDataOptionsChainProvider(OptionsChainProvider):
    """Theta REST (localhost:25503/v3). Short timeout, no retries. Returns [] on any error."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = CHAIN_REQUEST_TIMEOUT,
    ) -> None:
        import os

        # base_url kept for backwards compatibility; routing now via theta_v3_routes
        self.base_url = (base_url or os.getenv("THETA_REST_URL", "http://127.0.0.1:25503/v3")).rstrip("/")
        self.timeout = timeout

    def get_expirations(self, symbol: str) -> List[date]:
        """
        Fetch expirations for symbol. Returns sorted list of dates.
        
        Theta v3 returns HISTORICAL expirations by default under key "response".
        Historical expirations are VALID and must not cause failure.
        Returns all expirations sorted ascending (caller filters by DTE).
        """
        try:
            import httpx

            # v3: /option/list/expirations?symbol=SPY&format=json
            # Response shape: {"response":[{"symbol":"SPY","expiration":"YYYY-MM-DD"}, ...]}
            url = option_url("/list/expirations")
            params: Dict[str, Any] = {"symbol": (symbol or "").upper(), "format": "json"}
            headers = build_headers()
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(url, params=params, headers=headers)
                if r.status_code != 200:
                    logger.debug("[OptionsChain] get_expirations HTTP %d for %s", r.status_code, symbol)
                    return []
                ct = (r.headers.get("content-type") or "").lower()
                if "json" not in ct:
                    logger.debug("[OptionsChain] get_expirations non-JSON response for %s", symbol)
                    return []
                data = r.json()
                
                # Parse Theta v3 response shape: {"response":[...]}
                # Historical expirations are VALID - parse all
                expirations_list: List[Any] = []
                if isinstance(data, dict):
                    if "response" in data:
                        expirations_list = data["response"]
                    elif "expirations" in data:
                        expirations_list = data["expirations"]
                elif isinstance(data, list):
                    expirations_list = data
                
                if not expirations_list:
                    logger.debug("[OptionsChain] get_expirations empty response for %s", symbol)
                    return []
                
                out: List[date] = []
                for x in expirations_list:
                    if isinstance(x, dict):
                        # Extract expiration from {"symbol":"SPY","expiration":"YYYY-MM-DD"}
                        val = x.get("expiration") or x.get("date") or x.get("expiry")
                    else:
                        val = x
                    d = _parse_date_any(val)
                    if d is not None:
                        out.append(d)
                
                # NEVER return empty if response has data
                if not out and expirations_list:
                    logger.warning("[OptionsChain] get_expirations parsed 0 dates from %d items for %s", len(expirations_list), symbol)
                
                # Sort ascending and return all (caller filters by DTE)
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
        """
        Build options chain by:
        1. Fetch strikes for expiration
        2. Fetch pricing/greeks per contract using /option/snapshot/quote
        3. Normalize to standard shape
        
        Returns empty list on any error.
        """
        try:
            import httpx

            symbol_upper = (symbol or "").upper()
            exp_str = expiry.strftime("%Y%m%d")
            right_upper = (right or "P").upper()
            headers = build_headers()
            
            # Step 1: Fetch strikes for this expiration
            strikes_url = option_url("/list/strikes")
            strikes_params: Dict[str, Any] = {
                "symbol": symbol_upper,
                "expiration": exp_str,
                "format": "json",
            }
            
            strikes: List[float] = []
            with httpx.Client(timeout=self.timeout) as client:
                r_strikes = client.get(strikes_url, params=strikes_params, headers=headers)
                if r_strikes.status_code != 200:
                    logger.debug("[OptionsChain] get_chain strikes HTTP %d for %s %s", r_strikes.status_code, symbol_upper, exp_str)
                    return []
                try:
                    strikes_data = r_strikes.json()
                    # Strikes endpoint returns list of strike prices
                    if isinstance(strikes_data, list):
                        for s in strikes_data:
                            try:
                                strike_f = float(s)
                                strikes.append(strike_f)
                            except (TypeError, ValueError):
                                continue
                    elif isinstance(strikes_data, dict):
                        # Handle dict response if strikes are nested
                        strikes_list = strikes_data.get("strikes") or strikes_data.get("response") or []
                        for s in strikes_list:
                            try:
                                strike_f = float(s)
                                strikes.append(strike_f)
                            except (TypeError, ValueError):
                                continue
                except Exception as e:
                    logger.debug("[OptionsChain] get_chain failed to parse strikes: %s", e)
                    return []
            
            if not strikes:
                logger.debug("[OptionsChain] get_chain no strikes for %s %s", symbol_upper, exp_str)
                return []
            
            # Step 2: Fetch pricing/greeks for each strike using /option/snapshot/quote
            # Select ATM-centered strike window (configurable, default ±50)
            out: List[Dict[str, Any]] = []
            
            strikes_sorted = sorted(strikes)
            strike_window = 50  # Default ±50 strikes around middle (ATM-centered)
            if len(strikes_sorted) > (strike_window * 2):
                # Take middle strikes (ATM-centered window)
                mid_idx = len(strikes_sorted) // 2
                strikes_sorted = strikes_sorted[max(0, mid_idx - strike_window):mid_idx + strike_window]
            
            with httpx.Client(timeout=self.timeout * 2) as client:  # Longer timeout for multiple requests
                for strike in strikes_sorted:
                    try:
                        # Theta v3 contract snapshot: /option/snapshot/quote?symbol=SPY&expiration=YYYYMMDD&strike=450&right=P&format=json
                        snapshot_url = option_url("/snapshot/quote")
                        snapshot_params: Dict[str, Any] = {
                            "symbol": symbol_upper,
                            "expiration": exp_str,
                            "strike": strike,
                            "right": right_upper,
                            "format": "json",
                        }
                        r_snap = client.get(snapshot_url, params=snapshot_params, headers=headers, timeout=self.timeout)
                        if r_snap.status_code != 200:
                            continue  # Skip this strike if snapshot fails
                        
                        try:
                            snap_data = r_snap.json()
                            if not isinstance(snap_data, dict):
                                continue
                            
                            # Extract fields (field names may vary; try common variants)
                            # Graceful fallback if greeks are missing
                            bid = snap_data.get("bid") or snap_data.get("bid_price")
                            ask = snap_data.get("ask") or snap_data.get("ask_price")
                            delta = snap_data.get("delta")
                            iv = snap_data.get("implied_vol") or snap_data.get("iv") or snap_data.get("implied_volatility")
                            vol = snap_data.get("volume")
                            oi = snap_data.get("open_interest") or snap_data.get("oi")
                            
                            # Normalize strike (may come as integer cents or decimal)
                            strike_val = strike
                            if isinstance(snap_data.get("strike"), (int, float)):
                                strike_val = float(snap_data.get("strike"))
                            
                            # Normalize to EXACTLY existing internal structure
                            # Include all fields even if None (graceful fallback for missing greeks)
                            out.append({
                                "strike": strike_val,
                                "bid": bid,
                                "ask": ask,
                                "delta": delta,  # May be None if greeks unavailable
                                "iv": iv,  # May be None if greeks unavailable
                                "open_interest": oi,
                                "volume": vol,
                                "right": right_upper,
                                "expiry": expiry.isoformat(),  # Match codebase convention
                            })
                        except (ValueError, TypeError, KeyError) as e:
                            logger.debug("[OptionsChain] get_chain failed to parse snapshot for strike %s: %s", strike, e)
                            continue
                    except Exception as e:
                        logger.debug("[OptionsChain] get_chain snapshot request failed for strike %s: %s", strike, e)
                        continue
            
            return out
        except Exception as e:
            logger.debug("[OptionsChain] get_chain failed for %s %s %s: %s", symbol, expiry, right, e)
            return []


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
    """Wrapper that when inner returns zero expirations, optionally returns nearest weekly expirations within N days.

    OFF by default. Set OPTIONS_FALLBACK_WEEKLY_EXPIRATIONS=1 to enable.
    OPTIONS_FALLBACK_DAYS (default 14) limits how many days ahead to look.
    Clearly logged when fallback is used.
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
                    "[OptionsChain] Fallback: provider returned 0 expirations for %s; using %d weekly expiration(s) within %d days",
                    symbol,
                    len(fallback),
                    self._days,
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
    if len(s) >= 8 and s.isdigit():
        try:
            return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
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

# Theta v3 endpoints used:
# - GET /v3/option/list/expirations?symbol=SYMBOL&format=json
#   Response: {"response":[{"symbol":"SYMBOL","expiration":"YYYY-MM-DD"}, ...]}
# - GET /v3/option/list/strikes?symbol=SYMBOL&expiration=YYYYMMDD&format=json
#   Response: [strike1, strike2, ...] (list of strike prices)
# - GET /v3/option/snapshot/quote?symbol=SYMBOL&expiration=YYYYMMDD&strike=STRIKE&right=P|C&format=json
#   Response: {"bid": ..., "ask": ..., "delta": ..., "implied_vol": ..., "volume": ..., "open_interest": ...}
# 
# Note: Stock snapshots may return 403 (plan limitation) and are tested separately in diagnostics.
# Index endpoints are optional and tested separately.
