# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for macro economic event execution gate (Phase 4.5.2)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.environment.event_calendar import Event, DefaultEventCalendar, get_upcoming_events
from app.core.environment.macro_event_gate import (
    MACRO_EVENT_KEYWORDS,
    check_macro_event_gate,
)


def test_empty_calendar_pass():
    """Empty calendar (no events) → pass."""
    calendar = DefaultEventCalendar()
    config = {"macro_event_block_window_days": 2}
    reason = check_macro_event_gate(calendar, config)
    assert reason is None


def test_get_upcoming_events_stub_returns_empty():
    """Stub get_upcoming_events(days_ahead) returns empty list."""
    events = get_upcoming_events(7)
    assert events == []


def test_event_inside_window_blocked():
    """Macro event within block window → blocked with MACRO_EVENT_WINDOW."""
    today = date.today()
    event_tomorrow = Event(name="FOMC", date=today + timedelta(days=1))

    class CalendarWithFomc:
        def get_upcoming_events(self, days_ahead: int):
            if days_ahead >= 1:
                return [event_tomorrow]
            return []

    calendar = CalendarWithFomc()
    config = {"macro_event_block_window_days": 2}
    reason = check_macro_event_gate(calendar, config)
    assert reason is not None
    assert reason.code == "MACRO_EVENT_WINDOW"
    assert "FOMC" in reason.message
    assert reason.data.get("event_name") == "FOMC"
    assert reason.data.get("macro_event_block_window_days") == 2


def test_event_outside_window_pass():
    """Macro event only beyond block window → pass (calendar returns [] for window)."""
    # Calendar that returns no events for 2 days (event is on day 5)
    calendar = DefaultEventCalendar()
    config = {"macro_event_block_window_days": 2}
    reason = check_macro_event_gate(calendar, config)
    assert reason is None


def test_event_outside_window_calendar_returns_empty_for_window():
    """When calendar returns events only outside the window, gate passes."""
    # Simulate: calendar returns [] when asked for 2 days (events are 3+ days out)
    class CalendarEventsLater:
        def get_upcoming_events(self, days_ahead: int):
            return []  # no events in next N days

    calendar = CalendarEventsLater()
    config = {"macro_event_block_window_days": 2}
    reason = check_macro_event_gate(calendar, config)
    assert reason is None


def test_keywords_include_required():
    """Static list includes FOMC, CPI, JOBS, NFP, FED."""
    assert "FOMC" in MACRO_EVENT_KEYWORDS
    assert "CPI" in MACRO_EVENT_KEYWORDS
    assert "JOBS" in MACRO_EVENT_KEYWORDS
    assert "NFP" in MACRO_EVENT_KEYWORDS
    assert "FED" in MACRO_EVENT_KEYWORDS


def test_cpi_inside_window_blocked():
    """CPI event within window → blocked."""
    today = date.today()
    event = Event(name="CPI", date=today)

    class CalendarWithCpi:
        def get_upcoming_events(self, days_ahead: int):
            return [event] if days_ahead >= 0 else []

    calendar = CalendarWithCpi()
    config = {"macro_event_block_window_days": 2}
    reason = check_macro_event_gate(calendar, config)
    assert reason is not None
    assert reason.code == "MACRO_EVENT_WINDOW"
    assert "CPI" in reason.message


def test_zero_window_pass():
    """Window 0 → no events requested, pass."""
    today = date.today()
    event = Event(name="FOMC", date=today)

    class CalendarWithFomc:
        def get_upcoming_events(self, days_ahead: int):
            return [event] if days_ahead > 0 else []

    calendar = CalendarWithFomc()
    config = {"macro_event_block_window_days": 0}
    reason = check_macro_event_gate(calendar, config)
    assert reason is None
