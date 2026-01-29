# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market-hours utility (US/Eastern). Pragmatic weekday 9:30–16:00 ET."""

from __future__ import annotations

from datetime import datetime, time

try:
    from zoneinfo import ZoneInfo
    _UTC = ZoneInfo("UTC")
    _US_EASTERN = ZoneInfo("America/New_York")
except ImportError:
    import pytz
    _UTC = pytz.UTC
    _US_EASTERN = pytz.timezone("America/New_York")

MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)
POLL_INTERVAL_OPEN_SEC = 30
POLL_INTERVAL_CLOSED_SEC = 300


def is_market_open(utc_now: datetime | None = None) -> bool:
    """True if current US/Eastern time is weekday 9:30–16:00. Pragmatic (no holiday calendar)."""
    if utc_now is None:
        utc_now = datetime.now(_UTC)
    et = utc_now.astimezone(_US_EASTERN)
    if et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = et.time()
    return MARKET_OPEN <= t < MARKET_CLOSE


def get_polling_interval_seconds(utc_now: datetime | None = None) -> int:
    """Market open => 30s; market closed => 300s (5 min)."""
    return POLL_INTERVAL_OPEN_SEC if is_market_open(utc_now) else POLL_INTERVAL_CLOSED_SEC


def get_mode_label(provider_name: str, market_open: bool) -> str:
    """UI mode string: LIVE (ThetaTerminal) or LIVE (yfinance, stocks-only) or SNAPSHOT ONLY (...)."""
    if "SNAPSHOT ONLY" in provider_name:
        return provider_name
    if market_open:
        return f"LIVE ({provider_name})"
    return f"LIVE ({provider_name}) – market closed (slow refresh)"


__all__ = [
    "is_market_open",
    "get_polling_interval_seconds",
    "get_mode_label",
    "POLL_INTERVAL_OPEN_SEC",
    "POLL_INTERVAL_CLOSED_SEC",
]
