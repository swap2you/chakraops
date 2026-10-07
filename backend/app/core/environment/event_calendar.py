# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Event calendar for macro economic events (Phase 4.5.2 / R70-DEF-041).

Default production path uses ``StaticUsMacroCalendar`` (known FOMC dates for
current+next years). An empty stub MUST NOT be treated as "all clear" — callers
must pass ``provider_configured=True`` only when a real/static calendar is wired.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Sequence


@dataclass(frozen=True)
class Event:
    """A single calendar event (e.g. FOMC, CPI)."""

    name: str
    date: date


# Known FOMC meeting *decision* days (final day of two-day meetings) — static.
# Source: Federal Reserve published calendars (approximate; refresh annually).
_STATIC_FOMC_DATES: tuple[date, ...] = (
    # 2025
    date(2025, 1, 29),
    date(2025, 3, 19),
    date(2025, 5, 7),
    date(2025, 6, 18),
    date(2025, 7, 30),
    date(2025, 9, 17),
    date(2025, 10, 29),
    date(2025, 12, 10),
    # 2026
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
    # 2027 (placeholder mid-year cadence — refresh when Fed publishes)
    date(2027, 1, 27),
    date(2027, 3, 17),
    date(2027, 5, 5),
    date(2027, 6, 16),
    date(2027, 7, 28),
    date(2027, 9, 15),
    date(2027, 10, 27),
    date(2027, 12, 8),
)


def _first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    # weekday: Mon=0 … Fri=4
    offset = (4 - d.weekday()) % 7
    return d + timedelta(days=offset)


def _static_nfp_cpi_events(years: Sequence[int]) -> List[Event]:
    """Approximate NFP (first Friday) and CPI (mid-month Friday) markers."""
    out: List[Event] = []
    for y in years:
        for m in range(1, 13):
            nfp = _first_friday(y, m)
            out.append(Event(name="NFP", date=nfp))
            out.append(Event(name="JOBS", date=nfp))
            # CPI often mid-month; use the Friday on/after the 10th as a coarse marker.
            cpi_anchor = date(y, m, 10)
            cpi_offset = (4 - cpi_anchor.weekday()) % 7
            out.append(Event(name="CPI", date=cpi_anchor + timedelta(days=cpi_offset)))
    return out


class DefaultEventCalendar:
    """Empty stub calendar. Using this without provider_configured=True must fail closed."""

    PROVIDER_CONFIGURED = False

    def get_upcoming_events(self, days_ahead: int, *, as_of: Optional[date] = None) -> List[Event]:
        return []


class StaticUsMacroCalendar:
    """Minimal static US macro calendar (FOMC + approximate NFP/CPI).

    Marked ``provider_configured=True`` when used as the production default so an
    empty result means "no events in window", not "calendar missing".
    """

    PROVIDER_CONFIGURED = True

    def __init__(self, events: Optional[Sequence[Event]] = None) -> None:
        if events is not None:
            self._events = list(events)
        else:
            years = (date.today().year, date.today().year + 1)
            self._events = [Event(name="FOMC", date=d) for d in _STATIC_FOMC_DATES]
            self._events.extend(_static_nfp_cpi_events(years))

    def get_upcoming_events(self, days_ahead: int, *, as_of: Optional[date] = None) -> List[Event]:
        try:
            ahead = max(0, int(days_ahead))
        except (TypeError, ValueError):
            ahead = 0
        today = as_of if as_of is not None else date.today()
        end = today + timedelta(days=ahead)
        return [e for e in self._events if today <= e.date <= end]


_default_calendar: StaticUsMacroCalendar | DefaultEventCalendar = StaticUsMacroCalendar()


def get_upcoming_events(days_ahead: int) -> List[Event]:
    """Return macro events in the next days_ahead days from the default calendar."""
    return _default_calendar.get_upcoming_events(days_ahead)


def get_default_calendar() -> StaticUsMacroCalendar | DefaultEventCalendar:
    """Return the process-default calendar (static US macro unless tests override)."""
    return _default_calendar


def set_default_calendar(calendar: StaticUsMacroCalendar | DefaultEventCalendar) -> None:
    """Test helper: replace the process-default calendar."""
    global _default_calendar
    _default_calendar = calendar
