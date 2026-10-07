# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 4: Candle source — ORATS daily provider only (production)."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.eligibility.providers.orats_daily_provider import OratsDailyProvider

_provider: OratsDailyProvider | None = None


def _get_provider() -> OratsDailyProvider:
    global _provider
    if _provider is None:
        _provider = OratsDailyProvider()
    return _provider


def get_candles(
    symbol: str,
    timeframe: str = "daily",
    lookback: int = 400,
) -> List[Dict[str, Any]]:
    """
    Return daily OHLCV candles for symbol. Each item: {ts, open, high, low, close, volume}.
    Uses ORATS hist/dailies only. Empty => FAIL_NO_CANDLES in eligibility.
    """
    if (symbol or "").strip().upper() == "":
        return []
    provider = _get_provider()
    return provider.get_daily((symbol or "").strip().upper(), lookback=lookback)
