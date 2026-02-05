# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Macro economic event execution gate (Phase 4.5.2).

Blocks new trade proposals when a major economic event (FOMC, CPI, etc.)
falls within a configured window.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from app.signals.models import ExclusionReason

from app.core.environment.event_calendar import Event


# Static list of event keywords that trigger the gate
MACRO_EVENT_KEYWORDS = ["FOMC", "CPI", "JOBS", "NFP", "FED"]


class EventCalendar(Protocol):
    """Protocol for event calendar: provides get_upcoming_events(days_ahead)."""

    def get_upcoming_events(self, days_ahead: int) -> List[Event]:
        ...


def check_macro_event_gate(
    event_calendar: EventCalendar,
    config: Dict[str, Any],
) -> Optional[ExclusionReason]:
    """Return an ExclusionReason if a macro event is within the block window; else None.

    Fetches upcoming events for the configured window and blocks if any event
    name matches MACRO_EVENT_KEYWORDS (FOMC, CPI, JOBS, NFP, FED).

    Parameters
    ----------
    event_calendar : EventCalendar
        Provider of get_upcoming_events(days_ahead). Stub returns [] by default.
    config : dict
        Must contain "macro_event_block_window_days" (int). Events within this many days block.

    Returns
    -------
    Optional[ExclusionReason]
        MACRO_EVENT_WINDOW with message if blocked; None if pass.
    """
    window_days = config.get("macro_event_block_window_days", 2)
    try:
        window_days = int(window_days)
    except (TypeError, ValueError):
        window_days = 2

    if window_days <= 0:
        return None

    events = event_calendar.get_upcoming_events(window_days)
    keywords_upper = {k.upper() for k in MACRO_EVENT_KEYWORDS}

    for event in events:
        name = (event.name or "").strip().upper()
        if name and name in keywords_upper:
            return ExclusionReason(
                code="MACRO_EVENT_WINDOW",
                message=(
                    f"Macro event '{event.name}' within block window {window_days} days "
                    f"(date={event.date})"
                ),
                data={
                    "event_name": event.name,
                    "event_date": str(event.date),
                    "macro_event_block_window_days": window_days,
                },
            )

    return None
