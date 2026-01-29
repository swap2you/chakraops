# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for options data health gate (Phase 8)."""

import pytest

from app.core.gates.options_data_health import (
    REASON_NO_SYMBOLS_WITH_OPTIONS,
    OptionsDataHealthResult,
    evaluate_options_data_health,
)


def test_options_data_health_all_blocked():
    """When zero symbols have options, gate blocks with clear reason."""
    result = evaluate_options_data_health(
        symbols_with_options=[],
        symbols_without_options={"AAPL": "empty_chain", "AMZN": "NO_EXPIRATIONS"},
    )
    assert result.allowed is False
    assert result.valid_symbols_count == 0
    assert result.excluded_count == 2
    assert REASON_NO_SYMBOLS_WITH_OPTIONS in result.reasons


def test_options_data_health_partial_allowed():
    """When at least one symbol has options, gate allows (partial universe)."""
    result = evaluate_options_data_health(
        symbols_with_options=["SPY", "QQQ"],
        symbols_without_options={"AAPL": "empty_chain", "AMZN": "NO_EXPIRATIONS"},
    )
    assert result.allowed is True
    assert result.valid_symbols_count == 2
    assert result.excluded_count == 2
    assert result.reasons == []


def test_options_data_health_all_eligible():
    """When all symbols have options, gate allows."""
    result = evaluate_options_data_health(
        symbols_with_options=["SPY", "QQQ", "AAPL"],
        symbols_without_options={},
    )
    assert result.allowed is True
    assert result.valid_symbols_count == 3
    assert result.excluded_count == 0
