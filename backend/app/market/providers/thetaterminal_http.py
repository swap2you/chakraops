# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ThetaTerminal v3 HTTP provider (PRIMARY).

Base URL is configured via config.yaml or THETA_REST_URL environment variable.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.core.settings import get_theta_base_url, get_theta_timeout
from app.market.providers.base import MarketDataProviderInterface

logger = logging.getLogger(__name__)


def _get_theta_base() -> str:
    """Get Theta base URL from config (without /v3 suffix for this provider)."""
    url = get_theta_base_url()
    # Remove /v3 suffix if present (we add it back as THETA_V3_PREFIX)
    if url.endswith("/v3"):
        return url[:-3]
    return url


# These are now computed from centralized config
THETA_BASE_URL = None  # Set dynamically
THETA_V3_PREFIX = "/v3"
DEFAULT_TIMEOUT = 10.0


class ThetaTerminalHttpProvider(MarketDataProviderInterface):
    """Primary provider: ThetaTerminal v3 over HTTP. Robust health check; no crash on unreachable."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or _get_theta_base()).rstrip("/")
        self.v3_url = f"{self.base_url}{THETA_V3_PREFIX}"
        self.timeout = timeout if timeout is not None else get_theta_timeout()
        self._client: Optional[httpx.Client] = None

    def _client_get(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(base_url=self.v3_url, timeout=self.timeout)
        return self._client

    def health_check(self) -> Tuple[bool, str]:
        """Any simple endpoint returning 200 => ok. Do not raise."""
        try:
            r = self._client_get().get("/stock/list/symbols", params={"format": "json"})
            if r.status_code == 200:
                return True, "ThetaTerminal OK"
            return False, f"ThetaTerminal HTTP {r.status_code}"
        except Exception as e:
            return False, f"ThetaTerminal unreachable: {e}"

    def fetch_underlying_prices(self, symbols: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        client = self._client_get()
        for symbol in symbols:
            if not symbol or not isinstance(symbol, str):
                continue
            try:
                data = client.get(
                    "/stock/snapshot/trade",
                    params={"symbol": symbol, "format": "json"},
                )
                if data.status_code != 200:
                    continue
                j = data.json()
                if isinstance(j, dict) and "response" in j:
                    j = j["response"]
                if not isinstance(j, (list, dict)):
                    continue
                if isinstance(j, list) and len(j) > 0:
                    row = j[0]
                elif isinstance(j, dict):
                    row = j
                else:
                    continue
                for key in ("price", "last", "trade_price", "close"):
                    if key in row and row[key] is not None:
                        try:
                            p = float(row[key])
                            if p > 0:
                                out[symbol] = p
                                break
                        except (TypeError, ValueError):
                            continue
            except Exception as e:
                logger.debug("ThetaTerminal price %s: %s", symbol, e)
        return out

    def fetch_option_chain_availability(self, symbols: List[str]) -> Dict[str, bool]:
        out: Dict[str, bool] = {}
        client = self._client_get()
        for symbol in symbols:
            if not symbol or not isinstance(symbol, str):
                continue
            try:
                r = client.get(
                    "/stock/list/dates/trade",
                    params={"symbol": symbol, "format": "json"},
                )
                if r.status_code != 200:
                    out[symbol] = False
                else:
                    j = r.json() if r.content else None
                    if isinstance(j, dict) and "response" in j:
                        j = j["response"]
                    out[symbol] = bool(j and (isinstance(j, list) and len(j) > 0 or isinstance(j, dict)))
            except Exception:
                out[symbol] = False
        return out

    def fetch_iv_greeks(
        self,
        symbol: str,
        expiry: Optional[str] = None,
        strikes: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """ThetaTerminal can support this via options endpoints; not implemented here (best effort)."""
        return {}


__all__ = ["ThetaTerminalHttpProvider", "THETA_BASE_URL"]
