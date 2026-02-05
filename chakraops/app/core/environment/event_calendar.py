# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Event calendar for macro economic events (Phase 4.5.2).

Stub provider: get_upcoming_events(days_ahead) returns events in the next N days.
Initial implementation is static/mockable (empty by default).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List


@dataclass(frozen=True)
class Event:
    """A single calendar event (e.g. FOMC, CPI)."""

    name: str
    date: date


def get_upcoming_events(days_ahead: int) -> List[Event]:
    """Return macro events in the next days_ahead days.

    Stub implementation: returns empty list. Replace with real calendar
    or inject a provider in tests.

    Parameters
    ----------
    days_ahead : int
        Number of days to look ahead from today.

    Returns
    -------
    List[Event]
        Events with (name, date) in the window. Empty by default.
    """
    return _default_calendar.get_upcoming_events(days_ahead)


class DefaultEventCalendar:
    """Default stub calendar: no events. Use for production or override in tests."""

    def get_upcoming_events(self, days_ahead: int) -> List[Event]:
        """Return events in the next days_ahead days. Stub returns []."""
        return []


_default_calendar = DefaultEventCalendar()
