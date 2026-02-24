# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R23.4: Copilot output safety — forbidden patterns (FAIL_/WARN_/token) replaced by safe message."""

import pytest

from app.api.copilot import _sanity_answer, COPILOT_FORBIDDEN_PATTERNS


def test_sanity_answer_passes_clean_text():
    """Clean answer is returned unchanged."""
    text = "The symbol is not eligible because regime is DOWN and price is not near support."
    assert _sanity_answer(text) == text


def test_sanity_answer_rejects_fail_code():
    """Answer containing FAIL_* is replaced with safe message."""
    text = "The gate FAIL_STOCK_QUALITY caused the symbol to be blocked."
    out = _sanity_answer(text)
    assert "FAIL_" not in out
    assert "not have enough data" in out or "don't have enough data" in out


def test_sanity_answer_rejects_warn_code():
    """Answer containing WARN_* is replaced with safe message."""
    text = "Data is stale: WARN_ORATS_DELAYED."
    out = _sanity_answer(text)
    assert "WARN_" not in out


def test_sanity_answer_rejects_api_key():
    """Answer mentioning api key is replaced."""
    text = "Set the api_key in .env to enable."
    out = _sanity_answer(text)
    assert "not have enough data" in out or "don't have enough data" in out
    assert "api_key" not in out and ".env" not in out


def test_sanity_answer_rejects_token():
    """Answer mentioning token= or token: is replaced."""
    text = "Your token: sk-xxx must be kept secret."
    out = _sanity_answer(text)
    assert "sk-" not in out
    assert "not have enough data" in out or "don't" in out


def test_forbidden_patterns_defined():
    """Forbidden patterns list is non-empty and compiled."""
    assert len(COPILOT_FORBIDDEN_PATTERNS) >= 2
