"""R32.0: explicit event/earnings calendar availability state."""
from datetime import date

from app.core.data_reliability.event_calendar_status import (
    AVAILABLE,
    NO_PROVIDER_CONFIGURED,
    TOKEN_ABSENT,
    UNAVAILABLE,
    earnings_calendar_status,
    event_calendar_status,
)
from app.core.environment.event_calendar import Event


def test_default_macro_calendar_is_explicitly_unavailable():
    s = event_calendar_status(14)
    assert s.state == UNAVAILABLE
    assert s.reason == NO_PROVIDER_CONFIGURED
    assert s.available is False
    assert s.events == []


class _FakeCalendar:
    def get_upcoming_events(self, days_ahead):
        return [Event(name="FOMC", date=date(2026, 6, 25))]


def test_injected_provider_is_available():
    s = event_calendar_status(14, calendar=_FakeCalendar())
    assert s.state == AVAILABLE
    assert s.available is True
    assert len(s.events) == 1


class _BrokenCalendar:
    def get_upcoming_events(self, days_ahead):
        raise RuntimeError("boom")


def test_provider_error_is_unavailable_not_silent():
    s = event_calendar_status(14, calendar=_BrokenCalendar())
    assert s.state == UNAVAILABLE
    assert s.reason == "PROVIDER_ERROR"


def test_earnings_unavailable_without_token():
    s = earnings_calendar_status(token_present=False)
    assert s.state == UNAVAILABLE
    assert s.reason == TOKEN_ABSENT


def test_earnings_available_with_token():
    s = earnings_calendar_status(token_present=True)
    assert s.state == AVAILABLE
    assert s.reason == "OK"


def test_to_dict_shape():
    d = event_calendar_status(14).to_dict()
    assert d["kind"] == "macro_events"
    assert d["available"] is False
    assert "as_of_utc" in d
