# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Stock snapshot provider (yfinance). No Theta dependency.

- Normalizes to internal StockSnapshot.
- Does not apply universe filtering (handled in StockUniverseManager).
- Missing fields => None. No retries/caching (Phase 2).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.core.market.stock_models import StockSnapshot

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore


@dataclass(frozen=True)
class StockSnapshotFetchResult:
    snapshot: Optional[StockSnapshot]
    exclusion_reason: Optional[str]
    stock_available: bool


def _first_float(row: Dict[str, Any], keys: list) -> Optional[float]:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                return None
    return None


def _first_int(row: Dict[str, Any], keys: list) -> Optional[int]:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return int(float(row[k]))
            except (TypeError, ValueError):
                return None
    return None


class StockSnapshotProvider:
    """Fetch stock snapshot from yfinance and normalize to StockSnapshot."""

    def __init__(self, *, timeout_s: float = 5.0) -> None:
        self._timeout_s = float(timeout_s)

    def fetch_snapshot(self, symbol: str, *, has_options: bool) -> Tuple[Optional[StockSnapshot], Optional[str]]:
        """Fetch a single symbol snapshot. Returns (StockSnapshot, None) on success, (None, reason) on failure."""
        sym = (symbol or "").upper()
        if not sym:
            return None, "invalid_symbol"

        if yf is None:
            return None, "yfinance_not_installed"

        snapshot_time = datetime.now(timezone.utc)
        try:
            ticker = yf.Ticker(sym)
            info = getattr(ticker, "fast_info", None) or getattr(ticker, "info", None)
            if not info or not isinstance(info, dict):
                return None, "snapshot_empty_or_unexpected_shape"

            # fast_info uses different keys (e.g. lastPrice); info uses currentPrice, bid, ask
            price = _first_float(info, ["lastPrice", "currentPrice", "regularMarketPrice", "previousClose"])
            bid = _first_float(info, ["bid"])
            ask = _first_float(info, ["ask"])
            if price is None and bid is not None and ask is not None:
                price = (float(bid) + float(ask)) / 2.0
            volume = _first_int(info, ["volume", "regularMarketVolume"])
            avg_volume = _first_int(info, ["averageVolume", "averageVolume10days"])

            snap = StockSnapshot(
                symbol=sym,
                price=price,
                bid=bid,
                ask=ask,
                volume=volume,
                avg_volume=avg_volume,
                has_options=bool(has_options),
                snapshot_time=snapshot_time,
                data_source="YFINANCE",
            )
            return snap, None
        except Exception as e:
            logger.debug("StockSnapshotProvider fetch_snapshot %s: %s", sym, e)
            return None, f"snapshot_request_failed({type(e).__name__})"


__all__ = ["StockSnapshotProvider", "StockSnapshotFetchResult"]
