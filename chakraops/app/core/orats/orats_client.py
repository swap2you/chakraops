# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""ORATS Live client: probe, get_orats_live_strikes, get_orats_live_summaries. Base and paths from endpoints.py."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import requests

from app.core.orats.endpoints import BASE_DATAV2, PATH_LIVE_STRIKES, PATH_LIVE_SUMMARIES

logger = logging.getLogger(__name__)

ORATS_BASE = BASE_DATAV2
ORATS_LIVE_STRIKES = PATH_LIVE_STRIKES
ORATS_LIVE_SUMMARIES = PATH_LIVE_SUMMARIES
TIMEOUT_SEC = 10


class OratsUnavailableError(Exception):
    """Raised when ORATS probe or live fetch fails. Optional endpoint/symbol for API detail."""

    def __init__(
        self,
        message: str,
        http_status: int = 0,
        response_snippet: str = "",
        endpoint: str = "",
        symbol: str = "",
    ) -> None:
        self.http_status = http_status
        self.response_snippet = (response_snippet or "")[:500]
        self.endpoint = endpoint or ""
        self.symbol = symbol or ""
        super().__init__(message)


def _orats_get_live(endpoint_path: str, ticker: str, timeout_sec: float = TIMEOUT_SEC) -> tuple[Any, int, int]:
    """
    GET ORATS live endpoint (e.g. /live/strikes or /live/summaries). Returns (parsed_json, status_code, latency_ms).
    Logs [ORATS_CALL] endpoint= ticker= status= latency_ms= rows= (rows from list or data list).
    Raises OratsUnavailableError on request failure or non-200. Token from orats_secrets only.
    """
    from app.core.config.orats_secrets import ORATS_API_TOKEN
    url = f"{ORATS_BASE.rstrip('/')}{endpoint_path}"
    params: Dict[str, str] = {"token": ORATS_API_TOKEN, "ticker": ticker.upper()}
    t0 = time.perf_counter()
    try:
        r = requests.get(url, params=params, timeout=timeout_sec)
    except requests.RequestException as e:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("[ORATS_CALL] endpoint=%s ticker=%s status=FAIL latency_ms=%s error=%s", endpoint_path, ticker.upper(), latency_ms, e)
        print(f"[ORATS_CALL] endpoint={endpoint_path} ticker={ticker.upper()} status=FAIL latency_ms={latency_ms} rows=0")
        raise OratsUnavailableError(f"ORATS request failed: {e}", http_status=0, response_snippet=str(e)[:200], endpoint=endpoint_path, symbol=ticker.upper())

    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        raw: Any = r.json()
    except ValueError as e:
        logger.warning("[ORATS_CALL] endpoint=%s ticker=%s status=%s latency_ms=%s rows=0", endpoint_path, ticker.upper(), r.status_code, latency_ms)
        print(f"[ORATS_CALL] endpoint={endpoint_path} ticker={ticker.upper()} status={r.status_code} latency_ms={latency_ms} rows=0")
        raise OratsUnavailableError(f"ORATS invalid JSON: {e}", http_status=r.status_code, response_snippet=(r.text or "")[:200], endpoint=endpoint_path, symbol=ticker.upper())

    rows_count = 0
    rows_list: List[Any] = []
    if isinstance(raw, list):
        rows_list = raw
        rows_count = len(raw)
    elif isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        rows_list = raw["data"]
        rows_count = len(rows_list)
    quote_date: str | None = None
    field_presence: Dict[str, bool] = {}
    if rows_list and isinstance(rows_list[0], dict):
        first = rows_list[0]
        quote_date = first.get("quoteDate") or first.get("quote_date")
        field_presence = {
            "price": (first.get("stockPrice") is not None or first.get("stock_price") is not None),
            "volume": first.get("volume") is not None,
            "iv_rank": (first.get("ivRank1m") is not None or first.get("ivPct1m") is not None),
            "bid": first.get("bid") is not None,
            "ask": first.get("ask") is not None,
            "open_interest": first.get("openInterest") is not None,
        }
    logger.info(
        "[ORATS_CALL] endpoint=%s symbol=%s http_status=%s quote_date=%s fields=%s",
        endpoint_path, ticker.upper(), r.status_code, quote_date or "", field_presence,
    )
    print(f"[ORATS_CALL] endpoint={endpoint_path} symbol={ticker.upper()} status={r.status_code} latency_ms={latency_ms} rows={rows_count} quote_date={quote_date or ''} fields={field_presence}")

    if r.status_code != 200:
        snippet = (r.text or "")[:300]
        raise OratsUnavailableError(
            f"ORATS HTTP {r.status_code}",
            http_status=r.status_code,
            response_snippet=snippet,
            endpoint=endpoint_path,
            symbol=ticker.upper(),
        )

    return raw, r.status_code, latency_ms


def probe_orats_live(ticker: str = "SPY") -> dict:
    """
    Probe ORATS live strikes. Returns {"ok": True, "http_status": int, "row_count": int, "sample_keys": list}.
    Raises OratsUnavailableError on non-200, empty, or invalid response.
    """
    raw, status, _ = _orats_get_live(ORATS_LIVE_STRIKES, ticker)
    rows: List[Any] = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        rows = raw["data"]
    else:
        raise OratsUnavailableError(
            "ORATS response is not a list or {data: list}",
            http_status=200,
            response_snippet=str(raw)[:300],
            endpoint=ORATS_LIVE_STRIKES,
            symbol=ticker.upper(),
        )
    if not rows:
        raise OratsUnavailableError("ORATS response empty list", http_status=200, response_snippet="[]", endpoint=ORATS_LIVE_STRIKES, symbol=ticker.upper())
    first = rows[0]
    sample_keys = list(first.keys()) if isinstance(first, dict) else []
    return {"ok": True, "http_status": status, "row_count": len(rows), "sample_keys": sample_keys}


def get_orats_live_strikes(ticker: str, timeout_sec: float = TIMEOUT_SEC) -> List[Dict[str, Any]]:
    """GET /datav2/live/strikes for ticker. Returns list of strike rows. Logs [ORATS_CALL]. Validates and returns [] on empty."""
    raw, _, _ = _orats_get_live(ORATS_LIVE_STRIKES, ticker.upper(), timeout_sec)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        return raw["data"]
    return []


def get_orats_live_summaries(ticker: str, timeout_sec: float = TIMEOUT_SEC) -> List[Dict[str, Any]]:
    """GET /datav2/live/summaries for ticker. Returns list of summary rows (stockPrice, iv30d, etc.). Logs [ORATS_CALL]. Validates and returns [] on empty."""
    raw, _, _ = _orats_get_live(ORATS_LIVE_SUMMARIES, ticker.upper(), timeout_sec)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        return raw["data"]
    return []
