# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 8.3: Market-hours and polling interval."""

from __future__ import annotations

from datetime import datetime, time

import pytest

from app.market.market_hours import (
    is_market_open,
    get_polling_interval_seconds,
    get_mode_label,
    get_market_phase,
    get_eval_interval_seconds,
    EVAL_CADENCE_OPEN_SEC,
    POLL_INTERVAL_OPEN_SEC,
    POLL_INTERVAL_CLOSED_SEC,
)


def test_polling_interval_open_is_30() -> None:
    assert POLL_INTERVAL_OPEN_SEC == 30


def test_polling_interval_closed_is_300() -> None:
    assert POLL_INTERVAL_CLOSED_SEC == 300


def test_is_market_open_weekday_10et_returns_true() -> None:
    # Monday 10:00 ET -> open
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=ZoneInfo("UTC"))  # 10:00 ET
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=pytz.UTC)
    assert is_market_open(utc) is True


def test_is_market_open_weekday_17et_returns_false() -> None:
    # Monday 17:00 ET -> closed
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=pytz.UTC)
    assert is_market_open(utc) is False


def test_is_market_open_weekend_returns_false() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 25, 15, 0, 0, tzinfo=ZoneInfo("UTC"))  # Sunday 10 ET
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 25, 15, 0, 0, tzinfo=pytz.UTC)
    assert is_market_open(utc) is False


def test_get_polling_interval_seconds_open_30() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=pytz.UTC)
    assert get_polling_interval_seconds(utc) == POLL_INTERVAL_OPEN_SEC


def test_get_polling_interval_seconds_closed_300() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=pytz.UTC)
    assert get_polling_interval_seconds(utc) == POLL_INTERVAL_CLOSED_SEC


def test_get_mode_label_live_theta() -> None:
    assert "LIVE" in get_mode_label("ThetaTerminal", True)
    assert "ThetaTerminal" in get_mode_label("ThetaTerminal", True)


def test_get_mode_label_snapshot_only() -> None:
    assert "SNAPSHOT ONLY" in get_mode_label("SNAPSHOT ONLY (market closed / provider down)", False)


# Phase 10: market_phase
def test_get_market_phase_weekday_10et_returns_open() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=pytz.UTC)
    assert get_market_phase(utc) == "OPEN"


def test_get_market_phase_weekday_9et_returns_pre() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 14, 0, 0, tzinfo=ZoneInfo("UTC"))  # 9:00 ET
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 14, 0, 0, tzinfo=pytz.UTC)
    assert get_market_phase(utc) == "PRE"


def test_get_market_phase_weekday_17et_returns_post() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 22, 0, 0, tzinfo=pytz.UTC)
    assert get_market_phase(utc) == "POST"


def test_get_market_phase_weekend_returns_closed() -> None:
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 25, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 25, 15, 0, 0, tzinfo=pytz.UTC)
    assert get_market_phase(utc) == "CLOSED"


def test_get_eval_interval_seconds_open_is_900() -> None:
    assert EVAL_CADENCE_OPEN_SEC == 900
    try:
        from zoneinfo import ZoneInfo
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=ZoneInfo("UTC"))
    except ImportError:
        import pytz
        utc = datetime(2026, 1, 26, 15, 0, 0, tzinfo=pytz.UTC)
    assert get_eval_interval_seconds(utc) == EVAL_CADENCE_OPEN_SEC
