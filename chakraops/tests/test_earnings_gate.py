# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for earnings execution gate (Phase 4.5.1)."""

from __future__ import annotations

import pytest

from app.core.environment.earnings_gate import check_earnings_gate
from app.models.option_context import OptionContext


def test_earnings_within_window_blocked():
    """Earnings within block window → blocked with EARNINGS_WINDOW."""
    ctx = OptionContext(symbol="AAPL", days_to_earnings=3, event_flags=[])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is not None
    assert reason.code == "EARNINGS_WINDOW"
    assert "3" in reason.message and "7" in reason.message
    assert reason.data.get("days_to_earnings") == 3
    assert reason.data.get("earnings_block_window_days") == 7


def test_earnings_on_boundary_blocked():
    """days_to_earnings == window → blocked."""
    ctx = OptionContext(symbol="MSFT", days_to_earnings=7, event_flags=[])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is not None
    assert reason.code == "EARNINGS_WINDOW"


def test_earnings_outside_window_pass():
    """Earnings outside block window → pass."""
    ctx = OptionContext(symbol="AAPL", days_to_earnings=14, event_flags=[])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is None


def test_missing_days_to_earnings_pass():
    """Missing days_to_earnings (None) → pass."""
    ctx = OptionContext(symbol="AAPL", days_to_earnings=None, event_flags=[])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is None


def test_event_flag_earnings_blocked():
    """event_flags contains 'earnings' → blocked."""
    ctx = OptionContext(symbol="GOOGL", days_to_earnings=None, event_flags=["earnings"])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is not None
    assert reason.code == "EARNINGS_WINDOW"
    assert "event flag" in reason.message.lower() or "earnings" in reason.message.lower()
    assert "earnings" in (reason.data.get("event_flags") or [])


def test_event_flag_earnings_case_insensitive_blocked():
    """event_flags contains 'Earnings' (mixed case) → blocked."""
    ctx = OptionContext(symbol="GOOGL", days_to_earnings=None, event_flags=["Earnings"])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is not None
    assert reason.code == "EARNINGS_WINDOW"


def test_none_option_context_pass():
    """None option_context → pass (best-effort gate)."""
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(None, config)
    assert reason is None


def test_event_flag_other_pass():
    """event_flags with non-earnings (e.g. FOMC) and no days_to_earnings in window → pass."""
    ctx = OptionContext(symbol="AAPL", days_to_earnings=20, event_flags=["FOMC"])
    config = {"earnings_block_window_days": 7}
    reason = check_earnings_gate(ctx, config)
    assert reason is None
