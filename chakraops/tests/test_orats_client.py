# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for ORATS client response parsing (no live API calls)."""

import os
from unittest.mock import patch

import pytest

from app.core.options.providers.orats_client import (
    OratsAuthError,
    get_expirations,
    get_strikes_monthly,
    get_summaries,
)


def test_orats_auth_error_attributes():
    e = OratsAuthError(401, "Bad token")
    assert e.status_code == 401
    assert "token" in str(e).lower() or "401" in str(e)


@patch("app.core.options.providers.orats_client._get")
def test_get_expirations_parses_data_key(mock_get):
    mock_get.return_value = {"data": ["2026-02-21", "2026-03-20", "2026-04-17"]}
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_expirations("AAPL")
    assert out == ["2026-02-21", "2026-03-20", "2026-04-17"]
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[0][0] == "expirations"
    assert call_args[1]["params"].get("ticker") == "AAPL"


@patch("app.core.options.providers.orats_client._get")
def test_get_expirations_empty_response(mock_get):
    mock_get.return_value = {"data": []}
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_expirations("INVALID")
    assert out == []


@patch("app.core.options.providers.orats_client._get")
def test_get_expirations_list_response(mock_get):
    mock_get.return_value = ["2026-02-21", "2026-03-20"]
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_expirations("SPY")
    assert out == ["2026-02-21", "2026-03-20"]


@patch("app.core.options.providers.orats_client._get")
def test_get_strikes_monthly_parses_data_key(mock_get):
    mock_get.return_value = {
        "data": [
            {"strike": 450.0, "expirDate": "2026-02-21", "callBidPrice": 5.0, "putBidPrice": 4.0},
            {"strike": 455.0, "expirDate": "2026-02-21", "callBidPrice": 4.0, "putBidPrice": 3.5},
        ]
    }
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_strikes_monthly("AAPL", "2026-02-21")
    assert len(out) == 2
    assert out[0]["strike"] == 450.0
    assert out[1]["strike"] == 455.0
    call_args = mock_get.call_args
    assert "strikes/monthly" in call_args[0][0]
    assert call_args[1]["params"].get("expiry") == "2026-02-21"


@patch("app.core.options.providers.orats_client._get")
def test_get_strikes_monthly_empty(mock_get):
    mock_get.return_value = {"data": []}
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_strikes_monthly("XYZ", "2026-02-21")
    assert out == []


@patch("app.core.options.providers.orats_client._get")
def test_get_summaries_parses_data_key(mock_get):
    mock_get.return_value = {"data": [{"ticker": "SPY", "price": 450.0}]}
    with patch.dict(os.environ, {"ORATS_API_TOKEN": "test-token"}, clear=False):
        out = get_summaries("SPY")
    assert len(out) == 1
    assert out[0]["ticker"] == "SPY"
    assert out[0]["price"] == 450.0


@patch("app.core.options.providers.orats_client._get_token", return_value=None)
def test_get_expirations_raises_when_token_missing(mock_token):
    with pytest.raises(OratsAuthError):
        get_expirations("AAPL")
