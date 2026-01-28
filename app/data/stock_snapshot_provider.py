# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 2: Theta-backed stock snapshot provider.

IMPORTANT:
- This provider normalizes Theta v3 responses into the internal `StockSnapshot`.
- It MUST NOT apply filtering (universe filtering happens in StockUniverseManager).
- It MUST NOT throw on missing fields (missing => None).
- 403 from Theta = stock_available=False (plan limitation, not an error).
- No retries, no caching (Phase 2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.market.stock_models import StockSnapshot
from app.data.theta_v3_routes import build_headers, stock_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockSnapshotFetchResult:
    snapshot: Optional[StockSnapshot]
    exclusion_reason: Optional[str]
    stock_available: bool


class StockSnapshotProvider:
    """Fetch stock snapshot data from Theta v3 and normalize to StockSnapshot."""

    def __init__(self, *, timeout_s: float = 5.0) -> None:
        self._timeout_s = float(timeout_s)

    def fetch_snapshot(self, symbol: str, *, has_options: bool) -> Tuple[Optional[StockSnapshot], Optional[str]]:
        """Fetch a single symbol snapshot.

        Returns:
        - (StockSnapshot, None) on success (HTTP 200 + parseable payload)
        - (None, reason) when excluded due to plan limitation or invalid response
        """

        sym = (symbol or "").upper()
        if not sym:
            return None, "invalid_symbol"

        headers = build_headers()
        base_params: Dict[str, Any] = {"symbol": sym, "format": "json"}
        snapshot_time = datetime.now(timezone.utc)

        # Value plan commonly permits delayed quotes; Standard/Pro may permit trades.
        # Phase 2 rule: handle plan limitations gracefully (403 is not an "error").
        endpoints = ["/snapshot/quote", "/snapshot/trade"]

        resp: Optional[httpx.Response] = None
        last_exc: Optional[Exception] = None

        try:
            with httpx.Client(timeout=self._timeout_s) as client:
                for ep in endpoints:
                    url = stock_url(ep)
                    params: Dict[str, Any] = dict(base_params)
                    # Value plan: request 15-min delayed venue for quote snapshots (per Theta response guidance)
                    if ep == "/snapshot/quote":
                        params.setdefault("venue", "utp_cta")
                    try:
                        r = client.get(url, params=params, headers=headers)
                    except Exception as e:
                        last_exc = e
                        continue
                    # If we get a definitive response, stop trying other endpoints unless it's 404.
                    if r.status_code == 404:
                        continue
                    resp = r
                    break
        except Exception as e:
            last_exc = e

        if resp is None:
            return None, f"snapshot_request_failed({type(last_exc).__name__ if last_exc else 'unknown'})"

        if resp.status_code == 403:
            return None, "stock_snapshot_blocked_by_plan"

        if resp.status_code != 200:
            return None, f"snapshot_http_{resp.status_code}"

        try:
            payload = resp.json()
        except Exception:
            return None, "snapshot_invalid_json"

        # Theta v3 responses may be:
        # - {"response":[{...}]}  (wrapped)
        # - [{...}]              (list)
        # - {...}                (dict)
        row: Optional[Dict[str, Any]] = None
        if isinstance(payload, dict):
            if "response" in payload and isinstance(payload["response"], list) and payload["response"]:
                first = payload["response"][0]
                if isinstance(first, dict):
                    row = first
            else:
                row = payload
        elif isinstance(payload, list) and payload:
            first = payload[0]
            if isinstance(first, dict):
                row = first

        if not isinstance(row, dict) or not row:
            return None, "snapshot_empty_or_unexpected_shape"

        # Normalize fields (missing => None; zero allowed)
        price = _first_float(row, ["price", "last", "trade_price", "close"])
        bid = _first_float(row, ["bid", "bid_price"])
        ask = _first_float(row, ["ask", "ask_price"])
        # If provider does not include a last/price field, derive a best-effort midpoint.
        # This is normalization (not filtering) and enables Phase-2 hard filters to apply.
        if price is None and bid is not None and ask is not None:
            price = (float(bid) + float(ask)) / 2.0
        volume = _first_int(row, ["volume", "vol"])
        avg_volume = _first_int(row, ["avg_volume", "avgVol", "avg_volume_30d", "avgVol30"])

        snap = StockSnapshot(
            symbol=sym,
            price=price,
            bid=bid,
            ask=ask,
            volume=volume,
            avg_volume=avg_volume,
            has_options=bool(has_options),
            snapshot_time=snapshot_time,
            data_source="THETA",
        )
        return snap, None


def _first_float(row: Dict[str, Any], keys: list[str]) -> Optional[float]:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                return None
    return None


def _first_int(row: Dict[str, Any], keys: list[str]) -> Optional[int]:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return int(float(row[k]))
            except (TypeError, ValueError):
                return None
    return None


__all__ = ["StockSnapshotProvider", "StockSnapshotFetchResult"]

