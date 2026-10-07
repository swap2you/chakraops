# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Explicit availability state for the event / earnings calendar (R32.0).

The macro event calendar (``app.core.environment.event_calendar``) ships as a
stub with no configured provider. An empty event list from a stub MUST NOT be
interpreted as "no events, all clear" — that would be a silent assumption about
missing critical data. This module makes the state explicit:

- ``event_calendar_status`` returns AVAILABLE only when a real provider is
  injected; otherwise UNAVAILABLE with a reason code.
- ``earnings_calendar_status`` reports availability of the ORATS-backed
  earnings advisory, blocking explicitly when the token is absent.

No fallback provider is introduced. ORATS remains the sole market-data source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

# Reason codes (code-only labels).
NO_PROVIDER_CONFIGURED = "NO_PROVIDER_CONFIGURED"
TOKEN_ABSENT = "TOKEN_ABSENT"
PROVIDER_ERROR = "PROVIDER_ERROR"
OK = "OK"


def _now_iso(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class CalendarStatus:
    kind: str
    state: str
    reason: str
    as_of_utc: str
    events: List[Any] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.state == AVAILABLE

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "state": self.state,
            "available": self.available,
            "reason": self.reason,
            "as_of_utc": self.as_of_utc,
            "events": list(self.events),
        }


def event_calendar_status(
    days_ahead: int = 14,
    *,
    calendar: Optional[Any] = None,
    provider_configured: Optional[bool] = None,
    now: Optional[datetime] = None,
) -> CalendarStatus:
    """Return explicit AVAILABLE / UNAVAILABLE state for the macro calendar.

    A real or static calendar provider must be configured to be AVAILABLE.
    Empty stub without PROVIDER_CONFIGURED yields UNAVAILABLE so an empty list
    is never mistaken for a confident "no events" answer (R70-DEF-041).
    """
    as_of = _now_iso(now)

    if calendar is None:
        from app.core.environment.event_calendar import get_default_calendar

        calendar = get_default_calendar()

    if provider_configured is None:
        if hasattr(calendar, "PROVIDER_CONFIGURED"):
            provider_configured = bool(getattr(calendar, "PROVIDER_CONFIGURED"))
        else:
            # Explicitly injected calendar without the flag → treat as configured.
            provider_configured = True

    # Stub / unconfigured => not AVAILABLE.
    if not provider_configured:
        return CalendarStatus(
            kind="macro_events",
            state=UNAVAILABLE,
            reason=NO_PROVIDER_CONFIGURED,
            as_of_utc=as_of,
            events=[],
        )

    try:
        events = list(calendar.get_upcoming_events(days_ahead))
    except Exception:
        return CalendarStatus(
            kind="macro_events",
            state=UNAVAILABLE,
            reason=PROVIDER_ERROR,
            as_of_utc=as_of,
            events=[],
        )

    return CalendarStatus(
        kind="macro_events",
        state=AVAILABLE,
        reason=OK,
        as_of_utc=as_of,
        events=events,
    )


def earnings_calendar_status(
    *,
    token_present: Optional[bool] = None,
    now: Optional[datetime] = None,
) -> CalendarStatus:
    """Report ORATS-backed earnings-calendar availability (no network call).

    AVAILABLE only when the ORATS token is present; otherwise UNAVAILABLE with
    ``TOKEN_ABSENT`` (fail-loud, no fallback). Per-symbol earnings advisories
    are fetched elsewhere; this reports capability, not data.
    """
    as_of = _now_iso(now)
    if token_present is None:
        from app.core.config.orats_secrets import get_orats_token

        token_present = bool(get_orats_token())

    if not token_present:
        return CalendarStatus(
            kind="earnings",
            state=UNAVAILABLE,
            reason=TOKEN_ABSENT,
            as_of_utc=as_of,
            events=[],
        )
    return CalendarStatus(
        kind="earnings",
        state=AVAILABLE,
        reason=OK,
        as_of_utc=as_of,
        events=[],
    )
