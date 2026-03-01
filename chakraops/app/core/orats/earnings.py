# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""
R24.5 / R24.5.1: ORATS earnings advisory — request-time fields from /datav2/cores.
Used for hero pill and risk flags only; never blocks eligibility.
R24.5.1: Strict validation (reject 0000-00-00, bogus implied move); scaling fix for impliedEarningsMove.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.orats.orats_core_client import fetch_core_snapshot, OratsCoreError

logger = logging.getLogger(__name__)

# ORATS cores fields for earnings advisory (R24.5)
EARINGS_CORE_FIELDS = [
    "ticker",
    "nextErn",
    "daysToNextErn",
    "impliedEarningsMove",
    "quoteDate",
]

# Safe status values only — never FAIL_/WARN_ in API or UI
STATUS_OK = "OK"
STATUS_UNAVAILABLE = "Unavailable"
STATUS_STALE = "Stale"

# R24.5.1: Bogus/invalid nextErn values to reject
INVALID_NEXT_ERN_VALUES = frozenset({"", "0000-00-00", "0000-00-00T00:00:00", "null"})


def _parse_date(s: Any) -> Optional[str]:
    """Return YYYY-MM-DD or None. R24.5.1: Rejects 0000-00-00 and invalid dates."""
    if s is None:
        return None
    if isinstance(s, str):
        s = s.strip()[:10]
        if s in INVALID_NEXT_ERN_VALUES or s.startswith("0000-"):
            return None
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            if not _is_valid_next_ern(s):
                return None
            return s
        return None
    if hasattr(s, "strftime"):
        out = s.strftime("%Y-%m-%d")
        return None if out in INVALID_NEXT_ERN_VALUES or not _is_valid_next_ern(out) else out
    return None


def _is_valid_next_ern(date_str: Optional[str]) -> bool:
    """R24.5.1: True only if date is a plausible earnings date (reject 0000-00-00, invalid, zero day)."""
    if not date_str or len(date_str) != 10 or date_str in INVALID_NEXT_ERN_VALUES:
        return False
    try:
        from_d = datetime.strptime(date_str, "%Y-%m-%d").date()
        # Reject year 0, future > 10 years, or invalid month/day
        if from_d.year < 2000 or from_d.year > 2036:
            return False
        if from_d.month < 1 or from_d.month > 12:
            return False
        if from_d.day < 1 or from_d.day > 31:
            return False
        return True
    except (ValueError, TypeError):
        return False


def _as_of_date_ny(as_of_utc: Optional[datetime]) -> Optional[str]:
    """Return as_of date in America/New_York as YYYY-MM-DD."""
    if as_of_utc is None:
        return None
    try:
        import zoneinfo
        ny = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        try:
            from backports.zoneinfo import ZoneInfo
            ny = ZoneInfo("America/New_York")
        except ImportError:
            # Fallback: use UTC date
            if as_of_utc.tzinfo is None:
                as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)
            return as_of_utc.date().isoformat()
    if as_of_utc.tzinfo is None:
        as_of_utc = as_of_utc.replace(tzinfo=timezone.utc)
    return as_of_utc.astimezone(ny).date().isoformat()


def _calendar_days(from_date: str, to_date: str) -> Optional[int]:
    """Calendar days from from_date to to_date (YYYY-MM-DD). Positive = to_date in future."""
    if not from_date or not to_date or len(from_date) != 10 or len(to_date) != 10:
        return None
    try:
        from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
        return (to_d - from_d).days
    except (ValueError, TypeError):
        return None


def fetch_earnings_advisory(
    ticker: str,
    as_of_utc: Optional[datetime] = None,
    token: Optional[str] = None,
    timeout_sec: float = 15.0,
) -> Dict[str, Any]:
    """
    Fetch earnings advisory fields from ORATS /datav2/cores for a single ticker.
    Returns request-time fields only (not persisted in decision artifact).

    Returns dict with keys (all safe values; no FAIL_/WARN_):
      - earnings_next_date: YYYY-MM-DD or None
      - earnings_days: int (calendar days from as_of in America/New_York to next earnings), or None
      - earnings_annc_tod: "AMC" | "BMO" | "Unknown"
      - implied_earnings_move_pct: float or None
      - earnings_data_status: "OK" | "Unavailable" | "Stale"
      - earnings_as_of: ISO timestamp string
    """
    result: Dict[str, Any] = {
        "earnings_next_date": None,
        "earnings_days": None,
        "earnings_annc_tod": "Unknown",
        "implied_earnings_move_pct": None,
        "earnings_data_status": STATUS_UNAVAILABLE,
        "earnings_as_of": (as_of_utc or datetime.now(timezone.utc)).isoformat(),
    }
    if not token or not str(token).strip():
        return result
    try:
        core = fetch_core_snapshot(
            ticker,
            EARINGS_CORE_FIELDS,
            token.strip(),
            timeout_sec=timeout_sec,
        )
    except OratsCoreError as e:
        logger.debug("[ORATS_EARNINGS] ticker=%s error=%s", ticker, e)
        return result

    next_ern = _parse_date(core.get("nextErn"))
    days_to_next_ern = core.get("daysToNextErn")
    implied_move = core.get("impliedEarningsMove")
    quote_date_raw = core.get("quoteDate")

    # R24.5.1: Invalid nextErn (missing, 0000-00-00, invalid) => Unavailable, null all except earnings_as_of
    if not next_ern or not _is_valid_next_ern(next_ern):
        if quote_date_raw:
            if isinstance(quote_date_raw, str):
                result["earnings_as_of"] = quote_date_raw
            elif hasattr(quote_date_raw, "isoformat"):
                result["earnings_as_of"] = quote_date_raw.isoformat()
        return result

    result["earnings_next_date"] = next_ern

    # R24.5.1: Implied move scaling — 0 < v <= 1 => fraction (pct=value*100); 1 < v <= 50 => already percent; else null
    if implied_move is not None:
        try:
            v = float(implied_move)
            if 0 < v <= 1.0:
                result["implied_earnings_move_pct"] = v * 100.0
            elif 1.0 < v <= 50.0:
                result["implied_earnings_move_pct"] = v
            # else: invalid (e.g. 563) => leave null
        except (TypeError, ValueError):
            pass

    # earnings_days: use daysToNextErn if valid int >= 0; else compute calendar days from as_of (America/New_York) to next_ern
    as_of_dt = as_of_utc or datetime.now(timezone.utc)
    as_of_date_str = _as_of_date_ny(as_of_dt)
    if isinstance(days_to_next_ern, int) and days_to_next_ern >= 0:
        result["earnings_days"] = days_to_next_ern
    elif as_of_date_str and next_ern:
        days = _calendar_days(as_of_date_str, next_ern)
        if days is not None and days >= 0:
            result["earnings_days"] = days

    # earnings_as_of from quoteDate if available
    if quote_date_raw:
        if isinstance(quote_date_raw, str):
            result["earnings_as_of"] = quote_date_raw
        elif hasattr(quote_date_raw, "isoformat"):
            result["earnings_as_of"] = quote_date_raw.isoformat()

    # R24.5.1: Status OK only when next_ern valid AND earnings_days computed/valid
    if result["earnings_days"] is not None:
        result["earnings_data_status"] = STATUS_OK
        if quote_date_raw:
            try:
                if isinstance(quote_date_raw, str):
                    q = datetime.fromisoformat(quote_date_raw.replace("Z", "+00:00"))
                else:
                    q = quote_date_raw
                if q.tzinfo is None:
                    q = q.replace(tzinfo=timezone.utc)
                # Use as_of_dt for staleness so same inputs -> same status (deterministic)
                age = (as_of_dt - q).total_seconds()
                if age > 86400 * 2:  # > 2 days
                    result["earnings_data_status"] = STATUS_STALE
            except Exception:
                pass
    return result


def fetch_earnings_advisory_batch(
    tickers: list[str],
    as_of_utc: Optional[datetime] = None,
    token: Optional[str] = None,
    timeout_sec: float = 15.0,
) -> Dict[str, Dict[str, Any]]:
    """
    Fetch earnings advisory for multiple tickers (one request per ticker).
    Returns dict ticker -> earnings advisory dict (same shape as fetch_earnings_advisory).
    """
    out: Dict[str, Dict[str, Any]] = {}
    for t in tickers:
        sym = (t or "").strip().upper()
        if not sym:
            continue
        out[sym] = fetch_earnings_advisory(sym, as_of_utc=as_of_utc, token=token, timeout_sec=timeout_sec)
    return out
