# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Market-hours utility (US/Eastern). Pragmatic weekday 9:30–16:00 ET. Phase 10: market_phase."""

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
PRE_MARKET_END = time(9, 30)
POST_MARKET_START = time(16, 0)
POLL_INTERVAL_OPEN_SEC = 30
POLL_INTERVAL_CLOSED_SEC = 300
EVAL_CADENCE_OPEN_SEC = 900  # Phase 10: every 15 min during OPEN


MarketPhase = str  # "PRE" | "OPEN" | "MID" | "POST" | "CLOSED"


def get_market_phase(utc_now: datetime | None = None) -> MarketPhase:
    """Return PRE (before 9:30 ET), OPEN (9:30–16:00), POST (after 16:00), or CLOSED (weekend/holiday). MID = OPEN (same)."""
    if utc_now is None:
        utc_now = datetime.now(_UTC)
    et = utc_now.astimezone(_US_EASTERN)
    if et.weekday() >= 5:
        return "CLOSED"
    t = et.time()
    if t < PRE_MARKET_END:
        return "PRE"
    if t < MARKET_CLOSE:
        return "OPEN"
    return "POST"


def is_market_open(utc_now: datetime | None = None) -> bool:
    """True if current US/Eastern time is weekday 9:30–16:00. Pragmatic (no holiday calendar)."""
    return get_market_phase(utc_now) == "OPEN"


def get_chain_source(utc_now: datetime | None = None) -> str:
    """
    Single routing rule for ORATS chain endpoints.
    OPEN → LIVE (/datav2/live/…). Else (PRE/POST/CLOSED/HOLIDAY/WEEKEND) → DELAYED (/datav2/strikes, /datav2/strikes/options).
    """
    return "LIVE" if get_market_phase(utc_now) == "OPEN" else "DELAYED"


def get_polling_interval_seconds(utc_now: datetime | None = None) -> int:
    """Market open => 30s; market closed => 300s (5 min)."""
    return POLL_INTERVAL_OPEN_SEC if is_market_open(utc_now) else POLL_INTERVAL_CLOSED_SEC


def get_eval_interval_seconds(utc_now: datetime | None = None) -> int:
    """Phase 10: During OPEN use 15 min cadence; otherwise 5 min."""
    return EVAL_CADENCE_OPEN_SEC if is_market_open(utc_now) else POLL_INTERVAL_CLOSED_SEC


def get_mode_label(provider_name: str, market_open: bool) -> str:
    """UI mode string: LIVE (ThetaTerminal) or LIVE (yfinance, stocks-only) or SNAPSHOT ONLY (...)."""
    if "SNAPSHOT ONLY" in provider_name:
        return provider_name
    if market_open:
        return f"LIVE ({provider_name})"
    return f"LIVE ({provider_name}) – market closed (slow refresh)"


__all__ = [
    "is_market_open",
    "get_market_phase",
    "get_chain_source",
    "get_polling_interval_seconds",
    "get_eval_interval_seconds",
    "get_mode_label",
    "POLL_INTERVAL_OPEN_SEC",
    "POLL_INTERVAL_CLOSED_SEC",
    "EVAL_CADENCE_OPEN_SEC",
]
