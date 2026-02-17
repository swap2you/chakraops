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
    Single routing rule for ORATS chain endpoints (Stage-1, expirations, etc.).
    OPEN → LIVE (/datav2/live/…). Else (PRE/POST/CLOSED/HOLIDAY/WEEKEND) → DELAYED (/datav2/strikes, /datav2/strikes/options).
    """
    return "LIVE" if get_market_phase(utc_now) == "OPEN" else "DELAYED"


def get_stage2_chain_source(utc_now: datetime | None = None) -> str:
    """
    Chain source for Stage-2 option chain evaluation.
    Returns DELAYED always. The LIVE /datav2/live/strikes endpoint does not provide per-contract
    option_type (put/call), delta, bid, ask, OI in the shape our selector requires.
    DELAYED pipeline (/datav2/strikes + /datav2/strikes/options) yields full per-option records.
    """
    return "DELAYED"


def get_polling_interval_seconds(utc_now: datetime | None = None) -> int:
    """Market open => 30s; market closed => 300s (5 min)."""
    return POLL_INTERVAL_OPEN_SEC if is_market_open(utc_now) else POLL_INTERVAL_CLOSED_SEC


def get_eval_interval_seconds(utc_now: datetime | None = None) -> int:
    """Phase 10: During OPEN use 15 min cadence; otherwise 5 min."""
    return EVAL_CADENCE_OPEN_SEC if is_market_open(utc_now) else POLL_INTERVAL_CLOSED_SEC


def get_next_open_close_et(utc_now: datetime | None = None) -> tuple[str | None, str | None]:
    """
    Return (next_open_et, next_close_et) as ISO strings in ET.
    next_open_et: next 9:30 AM ET (today or next weekday).
    next_close_et: next 4:00 PM ET (today or next weekday).
    """
    from datetime import timedelta, time as dt_time
    if utc_now is None:
        utc_now = datetime.now(_UTC)
    et = utc_now.astimezone(_US_EASTERN)
    today = et.date()
    open_t = dt_time(9, 30, 0)
    close_t = dt_time(16, 0, 0)
    now_t = et.time()
    next_open = None
    next_close = None
    for d in range(8):
        cand = today + timedelta(days=d)
        if cand.weekday() >= 5:
            continue
        if next_open is None:
            open_dt = datetime.combine(cand, open_t, tzinfo=_US_EASTERN)
            if (d == 0 and now_t < open_t) or d > 0:
                next_open = open_dt
        if next_close is None:
            close_dt = datetime.combine(cand, close_t, tzinfo=_US_EASTERN)
            if (d == 0 and now_t < close_t) or d > 0:
                next_close = close_dt
        if next_open and next_close:
            break
    return (
        next_open.isoformat() if next_open else None,
        next_close.isoformat() if next_close else None,
    )


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
    "get_next_open_close_et",
    "get_chain_source",
    "get_stage2_chain_source",
    "get_polling_interval_seconds",
    "get_eval_interval_seconds",
    "get_mode_label",
    "POLL_INTERVAL_OPEN_SEC",
    "POLL_INTERVAL_CLOSED_SEC",
    "EVAL_CADENCE_OPEN_SEC",
]
