# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for market calendar and session gate (Phase 4.5.3)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.environment.market_calendar import (
    is_market_open_today,
    is_short_session,
    trading_days_until,
)
from app.core.environment.session_gate import check_session_gate


# --- market_calendar ---


def test_is_market_open_today_weekend():
    """Saturday and Sunday are not market open."""
    sat = date(2026, 1, 3)  # Saturday
    sun = date(2026, 1, 4)  # Sunday
    assert is_market_open_today(sat) is False
    assert is_market_open_today(sun) is False


def test_is_market_open_today_weekday():
    """Regular weekday (no holiday) is market open."""
    mon = date(2026, 1, 5)  # Monday
    assert is_market_open_today(mon) is True


def test_is_market_open_today_holiday():
    """New Year's Day and Christmas are closed."""
    assert is_market_open_today(date(2026, 1, 1)) is False
    assert is_market_open_today(date(2026, 12, 25)) is False


def test_trading_days_until_same_day():
    """expiry_date same as from_date -> 0 trading days."""
    d = date(2026, 1, 6)  # Tuesday
    assert trading_days_until(d, from_date=d) == 0


def test_trading_days_until_expiry_before_from():
    """expiry_date before from_date -> 0."""
    from_d = date(2026, 1, 8)
    expiry = date(2026, 1, 6)
    assert trading_days_until(expiry, from_date=from_d) == 0


def test_trading_days_until_next_day():
    """One trading day from Tue to Wed -> 1."""
    tue = date(2026, 1, 6)
    wed = date(2026, 1, 7)
    assert trading_days_until(wed, from_date=tue) == 1


def test_trading_days_until_skips_weekend():
    """Fri to next Mon: only Mon counts -> 1 trading day."""
    fri = date(2026, 1, 9)
    mon = date(2026, 1, 12)
    assert trading_days_until(mon, from_date=fri) == 1


def test_trading_days_until_uses_today_when_from_none():
    """When from_date is None, use date.today() (behavior: call doesn't crash)."""
    expiry = date(2026, 2, 1)
    n = trading_days_until(expiry)  # from_date=None -> today
    assert isinstance(n, int)
    assert n >= 0


def test_is_short_session_christmas_eve():
    """Dec 24 is short session."""
    assert is_short_session(date(2026, 12, 24)) is True
    assert is_short_session(date(2025, 12, 24)) is True


def test_is_short_session_day_after_thanksgiving():
    """Black Friday (day after Thanksgiving) is short session."""
    # 2025: Thanksgiving Nov 27 (Thu), Black Friday Nov 28
    assert is_short_session(date(2025, 11, 28)) is True
    # 2026: Thanksgiving Nov 26 (Thu), Black Friday Nov 27
    assert is_short_session(date(2026, 11, 27)) is True


def test_is_short_session_july_3_weekday():
    """July 3 when weekday is short session."""
    # July 3, 2026 is Friday
    assert is_short_session(date(2026, 7, 3)) is True


def test_is_short_session_regular_weekday():
    """Regular weekday is not short session."""
    assert is_short_session(date(2026, 1, 6)) is False  # Tuesday
    assert is_short_session(date(2026, 6, 15)) is False


# --- session_gate ---


def test_session_gate_short_session_blocks():
    """When today is short session and block_short_sessions True -> SHORT_SESSION."""
    today = date(2026, 12, 24)  # Christmas Eve
    config = {"block_short_sessions": True, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=date(2027, 1, 15), config=config)
    assert "SHORT_SESSION" in reasons


def test_session_gate_short_session_allowed_when_disabled():
    """When block_short_sessions False, short session does not add reason."""
    today = date(2026, 12, 24)
    config = {"block_short_sessions": False, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=date(2027, 1, 15), config=config)
    assert "SHORT_SESSION" not in reasons


def test_session_gate_insufficient_trading_days_blocks():
    """When trading_days_until(expiry) < min_trading_days_to_expiry -> INSUFFICIENT_TRADING_DAYS."""
    # Tue Jan 6, 2026 -> Wed Jan 7 = 1 trading day; min 5 -> block
    today = date(2026, 1, 6)
    expiry = date(2026, 1, 7)
    config = {"block_short_sessions": False, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=expiry, config=config)
    assert "INSUFFICIENT_TRADING_DAYS" in reasons


def test_session_gate_sufficient_trading_days_pass():
    """When trading days to expiry >= min -> no INSUFFICIENT_TRADING_DAYS."""
    # Use a far expiry so trading_days_until is large
    today = date(2026, 1, 6)
    expiry = date(2026, 2, 20)  # many trading days ahead
    config = {"block_short_sessions": False, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=expiry, config=config)
    assert "INSUFFICIENT_TRADING_DAYS" not in reasons


def test_session_gate_no_expiry_skips_trading_days_rule():
    """When expiry_date is None, INSUFFICIENT_TRADING_DAYS is not added."""
    today = date(2026, 1, 6)
    config = {"block_short_sessions": False, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=None, config=config)
    assert "INSUFFICIENT_TRADING_DAYS" not in reasons
    assert reasons == []


def test_session_gate_regular_day_and_sufficient_days_pass():
    """Regular weekday and sufficient trading days -> no reasons."""
    today = date(2026, 1, 6)  # Tuesday, not short session
    expiry = date(2026, 2, 20)
    config = {"block_short_sessions": True, "min_trading_days_to_expiry": 5}
    reasons = check_session_gate(today, expiry_date=expiry, config=config)
    assert reasons == []
