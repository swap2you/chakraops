# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Macro economic event execution gate (Phase 4.5.2 / R70-DEF-041).

Blocks new trade proposals when a major economic event (FOMC, CPI, etc.)
falls within a configured window. An unconfigured / stub calendar MUST NOT
silently pass as OPEN — fail closed with MACRO_CALENDAR_UNAVAILABLE.
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
    *,
    provider_configured: bool = False,
    as_of: Optional[Any] = None,
) -> Optional[ExclusionReason]:
    """Return an ExclusionReason if blocked or calendar unavailable; else None.

    Parameters
    ----------
    event_calendar : EventCalendar
        Provider of get_upcoming_events(days_ahead).
    config : dict
        Must contain "macro_event_block_window_days" (int).
    provider_configured : bool
        False (default) → fail closed with MACRO_CALENDAR_UNAVAILABLE.
        True → empty list means no events in window (pass); matching keywords block.
    as_of : date, optional
        Reference date for the look-ahead window (defaults to today inside calendar).

    Returns
    -------
    Optional[ExclusionReason]
        MACRO_CALENDAR_UNAVAILABLE, MACRO_EVENT_WINDOW, or None if pass.
    """
    if not provider_configured:
        return ExclusionReason(
            code="MACRO_CALENDAR_UNAVAILABLE",
            message=(
                "Macro event calendar provider not configured; "
                "fail-closed (UNAVAILABLE) — empty list is not all-clear"
            ),
            data={
                "state": "UNAVAILABLE",
                "reason": "NO_PROVIDER_CONFIGURED",
            },
        )

    window_days = config.get("macro_event_block_window_days", 2)
    try:
        window_days = int(window_days)
    except (TypeError, ValueError):
        window_days = 2

    if window_days <= 0:
        return None

    try:
        events = event_calendar.get_upcoming_events(window_days, as_of=as_of)  # type: ignore[call-arg]
    except TypeError:
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
