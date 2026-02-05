# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""US equity market calendar (Phase 4.5.3).

Provides trading days, holidays, and short (early-close) session awareness.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Set


def is_market_open_today(d: date) -> bool:
    """Return True if the US equity market is open on the given date.

    Closed on weekends and NYSE-observed US federal holidays.
    """
    if d.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return d not in _us_equity_holidays(d.year)


def trading_days_until(
    expiry_date: date,
    from_date: date | None = None,
) -> int:
    """Return the number of trading days from from_date (exclusive) through expiry_date (inclusive).

    So trading days in the half-open interval (from_date, expiry_date].
    If from_date is None, use today (date.today()).
    If expiry_date <= from_date, returns 0.
    """
    start = from_date if from_date is not None else date.today()
    if expiry_date <= start:
        return 0
    n = 0
    current = start
    while True:
        current += timedelta(days=1)
        if current > expiry_date:
            break
        if is_market_open_today(current):
            n += 1
    return n


def is_short_session(d: date) -> bool:
    """Return True if the given date is a short (early-close) session for US equities.

    Early close: Day after Thanksgiving (Black Friday), Christmas Eve (Dec 24),
    and July 3 when it is a weekday (day before Independence Day).
    """
    # Day after Thanksgiving: Friday after 4th Thursday of November
    if d.month == 11 and d.weekday() == 4:  # Friday
        # 4th Thursday is in 22-28
        thursday = d - timedelta(days=1)
        if 22 <= thursday.day <= 28:
            return True
    # Christmas Eve
    if d.month == 12 and d.day == 24:
        return True
    # July 3 (early close when weekday, day before Independence Day)
    if d.month == 7 and d.day == 3 and d.weekday() < 5:
        return True
    return False


def _us_equity_holidays(year: int) -> Set[date]:
    """Return set of US equity market (NYSE-style) holidays for the given year."""
    holidays: Set[date] = set()
    # New Year's Day
    holidays.add(date(year, 1, 1))
    # MLK Day: 3rd Monday in January
    holidays.add(_nth_weekday(year, 1, 0, 3))  # Monday=0
    # Presidents Day: 3rd Monday in February
    holidays.add(_nth_weekday(year, 2, 0, 3))
    # Good Friday: Friday before Easter (approximate: use simple rule or 2nd Friday in April for stub)
    # Common: Easter - 2 days; Easter is first Sun after first full moon after vernal equinox.
    # Simplified: use known Good Friday for a few years or weekday-based heuristic.
    holidays.add(_good_friday(year))
    # Memorial Day: last Monday in May
    holidays.add(_last_weekday(year, 5, 0))
    # Juneteenth: June 19
    holidays.add(date(year, 6, 19))
    # Independence Day: July 4
    holidays.add(date(year, 7, 4))
    # Labor Day: 1st Monday in September
    holidays.add(_nth_weekday(year, 9, 0, 1))
    # Thanksgiving: 4th Thursday in November
    thanksgiving = _nth_weekday(year, 11, 3, 4)  # Thursday=3
    holidays.add(thanksgiving)
    # Christmas
    holidays.add(date(year, 12, 25))
    return holidays


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth weekday (0=Mon, 6=Sun) in the given month."""
    first = date(year, month, 1)
    # days until first occurrence of weekday
    offset = (weekday - first.weekday()) % 7
    if offset < 0:
        offset += 7
    first_occurrence = first + timedelta(days=offset)
    return first_occurrence + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last weekday (0=Mon) in the given month."""
    if month == 12:
        next_first = date(year + 1, 1, 1)
    else:
        next_first = date(year, month + 1, 1)
    last_day = next_first - timedelta(days=1)
    # go back to last occurrence of weekday
    delta = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=delta)


def _easter(year: int) -> date:
    """Return Easter Sunday for the given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month = (h + L - 7 * m + 114) // 31
    day = ((h + L - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _good_friday(year: int) -> date:
    """Return Good Friday (Friday before Easter) for the given year."""
    easter_sunday = _easter(year)
    return easter_sunday - timedelta(days=2)
