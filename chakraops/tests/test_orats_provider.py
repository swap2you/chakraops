# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for ORATS provider parsing and behavior (no live API)."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.core.options.providers.orats_provider import (
    OratsOptionsChainProvider,
    _parse_date,
    _row_to_contracts,
)


def test_parse_date_iso_string():
    assert _parse_date("2026-02-21") == date(2026, 2, 21)
    assert _parse_date("2026-03-20") == date(2026, 3, 20)


def test_parse_date_slash_string():
    assert _parse_date("2026/02/21") == date(2026, 2, 21)


def test_parse_date_no_separator():
    assert _parse_date("20260221") == date(2026, 2, 21)


def test_parse_date_none_or_invalid():
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("invalid") is None
    assert _parse_date("2026-13-01") is None  # bad month


def test_row_to_contracts_put():
    row = {
        "strike": 450.0,
        "putBidPrice": 4.0,
        "putAskPrice": 4.5,
        "putValue": 4.25,
        "putMidIv": 0.20,
        "putOpenInterest": 1000,
        "putVolume": 50,
    }
    c = _row_to_contracts(row, "AAPL", "2026-02-21", "P")
    assert c is not None
    assert c["strike"] == 450.0
    assert c["bid"] == 4.0
    assert c["ask"] == 4.5
    assert c["right"] == "P"
    assert c["expiry"] == "2026-02-21"
    assert c["symbol"] == "AAPL"
    assert c["open_interest"] == 1000


def test_row_to_contracts_call():
    row = {
        "strike": 455.0,
        "callBidPrice": 3.0,
        "callAskPrice": 3.2,
        "callValue": 3.1,
        "callMidIv": 0.18,
        "callOpenInterest": 500,
    }
    c = _row_to_contracts(row, "SPY", "2026-03-20", "C")
    assert c is not None
    assert c["strike"] == 455.0
    assert c["bid"] == 3.0
    assert c["ask"] == 3.2
    assert c["right"] == "C"
    assert c["symbol"] == "SPY"


def test_row_to_contracts_missing_strike_returns_none():
    row = {"putBidPrice": 1.0, "putAskPrice": 1.1}
    assert _row_to_contracts(row, "AAPL", "2026-02-21", "P") is None


def test_orats_provider_get_expirations_empty_from_client():
    provider = OratsOptionsChainProvider()
    with patch("app.core.options.providers.orats_provider.get_expirations", return_value=[]):
        out = provider.get_expirations("INVALID")
    assert out == []


def test_orats_provider_get_expirations_parses_dates():
    provider = OratsOptionsChainProvider()
    with patch(
        "app.core.options.providers.orats_provider.get_expirations",
        return_value=["2026-02-21", "2026-03-20"],
    ):
        out = provider.get_expirations("AAPL")
    assert len(out) == 2
    assert out[0] == date(2026, 2, 21)
    assert out[1] == date(2026, 3, 20)
    assert out == sorted(out)


def test_orats_provider_get_chain_uses_strikes_monthly():
    provider = OratsOptionsChainProvider()
    rows = [
        {"strike": 100.0, "putBidPrice": 1.0, "putAskPrice": 1.1},
        {"strike": 101.0, "putBidPrice": 0.9, "putAskPrice": 1.0},
    ]
    with patch(
        "app.core.options.providers.orats_provider.get_strikes_monthly",
        return_value=rows,
    ):
        out = provider.get_chain("SPY", date(2026, 2, 21), "P")
    assert len(out) == 2
    assert out[0]["strike"] == 100.0 and out[0]["right"] == "P"
    assert out[1]["strike"] == 101.0


def test_orats_provider_get_full_chain_no_expirations():
    provider = OratsOptionsChainProvider()
    with patch.object(provider, "get_expirations", return_value=[]):
        full = provider.get_full_chain("XYZ", dte_min=7, dte_max=45)
    assert full["chain_status"] == "no_expirations"
    assert full["contract_count"] == 0
    assert "error" in full
