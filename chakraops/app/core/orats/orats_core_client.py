# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
ORATS Core Data v2 client — single source of truth for per-ticker snapshot.

Phase 8A: GET /datav2/cores returns all required per-ticker equity + options context.
Phase 8.8: Optional cache layer via fetch_with_cache (TTL 1 day for cores).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_CORES, PATH_HIST_DAILIES, url_cores, url_hist_dailies

logger = logging.getLogger(__name__)

# Phase 8D: cache for derived avg_stock_volume_20d (ticker -> {date -> value})
_hist_dailies_avg_cache: Dict[str, Dict[str, float]] = {}

DEFAULT_TIMEOUT_SEC = 15.0


class OratsCoreError(Exception):
    """Raised when /datav2/cores request fails or returns no usable data."""

    def __init__(
        self,
        message: str,
        ticker: str = "",
        http_status: Optional[int] = None,
        response_snippet: str = "",
    ) -> None:
        self.ticker = ticker
        self.http_status = http_status
        self.response_snippet = (response_snippet or "")[:500]
        super().__init__(message)


def fetch_core_snapshot(
    ticker: str,
    fields: List[str],
    token: str,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Dict[str, Any]:
    """
    Call GET /datav2/cores and return a normalized per-ticker snapshot.

    Args:
        ticker: Symbol (e.g. AAPL).
        fields: ORATS field names to request (e.g. ["stkVolu", "avgOptVolu20d", "ivPctile1y"]).
        token: ORATS API token.
        timeout_sec: Request timeout.

    Returns:
        Single row as dict (ORATS field names → values). Empty dict if data[] is empty
        or missing; no silent defaults.

    Raises:
        OratsCoreError: On HTTP errors, empty data[], or invalid response shape.
    """
    if not token or not str(token).strip():
        raise OratsCoreError("ORATS token is empty", ticker=ticker)
    ticker_upper = str(ticker).strip().upper()
    if not ticker_upper:
        raise OratsCoreError("Ticker is empty", ticker=ticker)

    url = url_cores(BASE_DATAV2)
    params: Dict[str, str] = {
        "token": token.strip(),
        "ticker": ticker_upper,
    }
    if fields:
        params["fields"] = ",".join(str(f).strip() for f in fields if str(f).strip())

    params_for_cache: Dict[str, Any] = {"as_of": date.today().isoformat()}

    def _do_fetch() -> Dict[str, Any]:
        try:
            resp = requests.get(url, params=params, timeout=timeout_sec)
        except requests.RequestException as e:
            raise OratsCoreError(
                f"Request failed: {e}",
                ticker=ticker_upper,
                response_snippet=str(e)[:200],
            ) from e
        if resp.status_code != 200:
            snippet = resp.text[:300] if resp.text else ""
            raise OratsCoreError(
                f"ORATS cores returned HTTP {resp.status_code}",
                ticker=ticker_upper,
                http_status=resp.status_code,
                response_snippet=snippet,
            )
        try:
            raw: Any = resp.json()
        except Exception as e:
            raise OratsCoreError(
                f"Invalid JSON response: {e}",
                ticker=ticker_upper,
                response_snippet=resp.text[:200] if resp.text else "",
            ) from e
        rows: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict) and "data" in raw:
            d = raw.get("data")
            if isinstance(d, list):
                rows = d
        if not rows:
            raise OratsCoreError(
                "ORATS cores returned empty data[]",
                ticker=ticker_upper,
                http_status=200,
                response_snippet=str(raw)[:200] if raw else "",
            )
        return dict(rows[0])

    try:
        from app.core.data.cache_store import TTL_IV_RANK, fetch_with_cache
        snapshot = fetch_with_cache("cores", ticker_upper, params_for_cache, TTL_IV_RANK, _do_fetch)
        return snapshot
    except ImportError:
        pass
    except OratsCoreError:
        raise

    try:
        resp = requests.get(url, params=params, timeout=timeout_sec)
    except requests.RequestException as e:
        logger.warning("[ORATS_CORE] ticker=%s request failed: %s", ticker_upper, e)
        raise OratsCoreError(
            f"Request failed: {e}",
            ticker=ticker_upper,
            response_snippet=str(e)[:200],
        ) from e

    if resp.status_code != 200:
        snippet = resp.text[:300] if resp.text else ""
        logger.warning("[ORATS_CORE] ticker=%s HTTP %s %s", ticker_upper, resp.status_code, snippet)
        raise OratsCoreError(
            f"ORATS cores returned HTTP {resp.status_code}",
            ticker=ticker_upper,
            http_status=resp.status_code,
            response_snippet=snippet,
        )

    try:
        raw: Any = resp.json()
    except Exception as e:
        logger.warning("[ORATS_CORE] ticker=%s invalid JSON: %s", ticker_upper, e)
        raise OratsCoreError(
            f"Invalid JSON response: {e}",
            ticker=ticker_upper,
            response_snippet=resp.text[:200] if resp.text else "",
        ) from e

    # Handle data[] — may be list or { "data": list }
    rows: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw:
        d = raw.get("data")
        if isinstance(d, list):
            rows = d

    if not rows:
        raise OratsCoreError(
            "ORATS cores returned empty data[]",
            ticker=ticker_upper,
            http_status=200,
            response_snippet=str(raw)[:200] if raw else "",
        )

    # First row is the per-ticker snapshot (cores typically one row per ticker)
    snapshot = dict(rows[0])
    # Field absence: do not add keys that were not returned; caller checks presence
    return snapshot


def fetch_hist_dailies(
    ticker: str,
    token: str,
    fields: Optional[List[str]] = None,
    days: int = 20,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> List[Dict[str, Any]]:
    """
    GET /datav2/hist/dailies for ticker. Returns list of daily rows (newest first typically).
    Used for derived avg_stock_volume_20d (Phase 8D).
    """
    if not token or not str(token).strip():
        return []
    ticker_upper = str(ticker).strip().upper()
    url = url_hist_dailies(BASE_DATAV2)
    params: Dict[str, Any] = {"token": token.strip(), "ticker": ticker_upper}
    if fields:
        params["fields"] = ",".join(str(f).strip() for f in fields if str(f).strip())
    try:
        resp = requests.get(url, params=params, timeout=timeout_sec)
        if resp.status_code != 200:
            return []
        raw = resp.json()
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw and isinstance(raw.get("data"), list):
        rows = raw["data"]
    return rows[: days] if rows else []


def derive_avg_stock_volume_20d(
    ticker: str,
    token: str,
    trade_date: Optional[str] = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
) -> Optional[float]:
    """
    Compute 20-day average stock volume from /datav2/hist/dailies. Cached per ticker per day.
    Returns None if unavailable; does not block. Phase 8D.
    """
    from datetime import datetime, timezone

    ticker_upper = str(ticker).strip().upper()
    date_key = trade_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if ticker_upper not in _hist_dailies_avg_cache:
        _hist_dailies_avg_cache[ticker_upper] = {}
    if date_key in _hist_dailies_avg_cache[ticker_upper]:
        return _hist_dailies_avg_cache[ticker_upper][date_key]

    rows = fetch_hist_dailies(
        ticker_upper,
        token,
        fields=["tradeDate", "stockVolume"],
        days=20,
        timeout_sec=timeout_sec,
    )
    volumes: List[float] = []
    for row in rows:
        v = row.get("stockVolume") or row.get("stockVolu")
        if v is not None:
            try:
                volumes.append(float(v))
            except (TypeError, ValueError):
                pass
    if len(volumes) < 1:
        _hist_dailies_avg_cache[ticker_upper][date_key] = None
        return None
    avg = sum(volumes) / len(volumes)
    _hist_dailies_avg_cache[ticker_upper][date_key] = avg
    return avg
