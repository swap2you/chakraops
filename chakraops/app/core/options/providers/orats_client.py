# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS Live Data API client. Token from env ORATS_API_TOKEN only."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ORATS_BASE_URL = "https://api.orats.io/datav2/live"
DEFAULT_TIMEOUT = 30.0
MAX_RETRIES_429 = 3
BACKOFF_BASE_SEC = 2.0


class OratsAuthError(Exception):
    """Raised on 401/403 from ORATS API. Do not log token."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class OratsDataUnavailableError(OratsAuthError):
    """ORATS returned no usable data: empty, 4xx, entitlement, or missing required fields. Do not treat as success. Subclasses OratsAuthError so except OratsAuthError still catches 401/403."""

    def __init__(
        self,
        endpoint: str,
        symbol: str,
        http_status: int,
        response_snippet: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        self.endpoint = endpoint
        self.symbol = symbol
        self.http_status = http_status
        self.response_snippet = (response_snippet or "")[:500]
        msg = message or f"ORATS {endpoint} symbol={symbol} HTTP {http_status}"
        if self.response_snippet:
            msg += f" — {self.response_snippet[:200]}"
        super().__init__(http_status, msg)


def _get_token() -> Optional[str]:
    """Token from env only (ORATS_API_KEY or ORATS_API_TOKEN). Never hardcode."""
    return (os.getenv("ORATS_API_KEY") or os.getenv("ORATS_API_TOKEN") or "").strip() or None


def _get(
    path: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    session: Optional[requests.Session] = None,
) -> Any:
    """GET ORATS live endpoint. Injects token from ORATS_API_TOKEN. Retries on 429."""
    token = _get_token()
    if not token:
        logger.warning("ORATS_API_TOKEN is not set; ORATS requests will fail")
        raise OratsAuthError(401, "ORATS_API_TOKEN is not set")

    url = f"{ORATS_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    params = dict(params or {})
    params["token"] = token

    session = session or requests.Session()
    last_exc: Optional[Exception] = None

    for attempt in range(MAX_RETRIES_429 + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as e:
            logger.warning("ORATS request failed: %s", e)
            raise

        if resp.status_code in (401, 403):
            logger.warning("ORATS auth failed: HTTP %s", resp.status_code)
            snippet = (resp.text or "").strip()[:300]
            if "entitlement" in snippet.lower() or "permission" in snippet.lower():
                snippet = snippet[:200]
            raise OratsDataUnavailableError(
                endpoint=path.split("?")[0],
                symbol=(params.get("ticker") or "").upper(),
                http_status=resp.status_code,
                response_snippet=snippet or None,
                message=f"ORATS API auth failed (HTTP {resp.status_code}). Check ORATS_API_TOKEN.",
            )

        if resp.status_code == 429:
            if attempt < MAX_RETRIES_429:
                backoff = BACKOFF_BASE_SEC ** (attempt + 1)
                logger.warning("ORATS rate limit (429); retry in %.1fs (attempt %d)", backoff, attempt + 1)
                time.sleep(backoff)
                continue
            logger.error("ORATS rate limit (429) after %d retries", MAX_RETRIES_429)
            raise OratsDataUnavailableError(
                endpoint=path.split("?")[0],
                symbol=(params.get("ticker") or "").upper(),
                http_status=429,
                response_snippet=(resp.text or "")[:200],
                message="ORATS API rate limit exceeded. Wait before retrying.",
            )

        if resp.status_code != 200:
            body_preview = (resp.text or "")[:200]
            logger.warning("ORATS HTTP %s: %s", resp.status_code, body_preview)
            raise OratsDataUnavailableError(
                endpoint=path.split("?")[0],
                symbol=(params.get("ticker") or "").upper(),
                http_status=resp.status_code,
                response_snippet=body_preview,
            )

        try:
            return resp.json()
        except ValueError as e:
            logger.warning("ORATS invalid JSON: %s", e)
            raise ValueError(f"ORATS API returned invalid JSON: {e}") from e

    raise last_exc or ValueError("ORATS request failed")


def get_expirations(ticker: str, include_strikes: bool = False, **kwargs: Any) -> List[Any]:
    """GET /expirations?ticker=... Returns list of date strings or list of {expiration, strikes}."""
    params: Dict[str, Any] = {"ticker": ticker.upper()}
    if include_strikes:
        params["include"] = "true"
    data = _get("expirations", params=params, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_strikes(ticker: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /strikes?ticker=... Returns list of strike rows (each has expirDate, strike, call/put fields)."""
    data = _get("strikes", params={"ticker": ticker.upper()}, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_strikes_monthly(ticker: str, expiry: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /strikes/monthly?ticker=...&expiry=... Expiry can be comma-separated. Returns list of strike rows."""
    params: Dict[str, Any] = {"ticker": ticker.upper(), "expiry": expiry}
    data = _get("strikes/monthly", params=params, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_summaries(ticker: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /summaries?ticker=... Returns SMV summaries (impliedMove, iv30d, iv90d, skewing, etc.)."""
    data = _get("summaries", params={"ticker": ticker.upper()}, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_iv_rank(ticker: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /ivrank?ticker=... Returns IV rank data (ivRank1y, ivPct1y, etc.)."""
    data = _get("ivrank", params={"ticker": ticker.upper()}, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_cores(ticker: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /cores?ticker=... Returns core data (daysToNextErn, nextErn, ivPctile1y, etc.)."""
    data = _get("cores", params={"ticker": ticker.upper()}, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


def get_monies_forecast(ticker: str, **kwargs: Any) -> List[Dict[str, Any]]:
    """GET /monies/forecast?ticker=... Returns forecast monies (optional; for expected move)."""
    data = _get("monies/forecast", params={"ticker": ticker.upper()}, **kwargs)
    if isinstance(data, dict) and "data" in data:
        return data["data"] if isinstance(data["data"], list) else []
    if isinstance(data, list):
        return data
    return []


class OratsClient:
    """Thin wrapper over _get and helpers. Token from ORATS_API_TOKEN only."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._session = requests.Session()

    def get_expirations(self, ticker: str, include_strikes: bool = False) -> List[Any]:
        return get_expirations(ticker, include_strikes=include_strikes, timeout=self.timeout, session=self._session)

    def get_strikes(self, ticker: str) -> List[Dict[str, Any]]:
        return get_strikes(ticker, timeout=self.timeout, session=self._session)

    def get_strikes_monthly(self, ticker: str, expiry: str) -> List[Dict[str, Any]]:
        return get_strikes_monthly(ticker, expiry, timeout=self.timeout, session=self._session)

    def get_summaries(self, ticker: str) -> List[Dict[str, Any]]:
        return get_summaries(ticker, timeout=self.timeout, session=self._session)

    def get_iv_rank(self, ticker: str) -> List[Dict[str, Any]]:
        return get_iv_rank(ticker, timeout=self.timeout, session=self._session)

    def get_cores(self, ticker: str) -> List[Dict[str, Any]]:
        return get_cores(ticker, timeout=self.timeout, session=self._session)

    def get_monies_forecast(self, ticker: str) -> List[Dict[str, Any]]:
        return get_monies_forecast(ticker, timeout=self.timeout, session=self._session)


__all__ = [
    "OratsAuthError",
    "OratsDataUnavailableError",
    "OratsClient",
    "ORATS_BASE_URL",
    "get_live_summary",
    "get_expirations",
    "get_strikes",
    "get_strikes_monthly",
    "get_summaries",
    "get_iv_rank",
    "get_cores",
    "get_monies_forecast",
]
