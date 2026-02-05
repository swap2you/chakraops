# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Unit tests for OptionContext and OratsOptionsChainProvider.get_option_context."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.models.option_context import OptionContext, option_context_from_dict
from app.core.options.providers.orats_provider import OratsOptionsChainProvider
from app.core.options.providers.orats_client import OratsAuthError


# --- OptionContext dataclass ---


def test_option_context_minimal():
    ctx = OptionContext(symbol="AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd is None
    assert ctx.iv_rank is None
    assert ctx.iv_percentile is None
    assert ctx.term_structure_slope is None
    assert ctx.skew_metric is None
    assert ctx.days_to_earnings is None
    assert ctx.event_flags == []
    assert ctx.raw == {}


def test_option_context_all_fields():
    ctx = OptionContext(
        symbol="MSFT",
        expected_move_1sd=0.05,
        iv_rank=45.0,
        iv_percentile=67.0,
        term_structure_slope=-0.02,
        skew_metric=-0.07,
        days_to_earnings=14,
        event_flags=["FOMC"],
        raw={"summaries": {}},
    )
    assert ctx.symbol == "MSFT"
    assert ctx.expected_move_1sd == 0.05
    assert ctx.iv_rank == 45.0
    assert ctx.iv_percentile == 67.0
    assert ctx.term_structure_slope == -0.02
    assert ctx.skew_metric == -0.07
    assert ctx.days_to_earnings == 14
    assert ctx.event_flags == ["FOMC"]
    assert "summaries" in ctx.raw


def test_option_context_to_dict():
    ctx = OptionContext(
        symbol="SPY",
        expected_move_1sd=0.03,
        iv_rank=30.0,
        event_flags=[],
    )
    d = ctx.to_dict()
    assert d["symbol"] == "SPY"
    assert d["expected_move_1sd"] == 0.03
    assert d["iv_rank"] == 30.0
    assert d["event_flags"] == []
    assert "raw_keys" in d


def test_option_context_from_dict():
    data = {
        "symbol": "AAPL",
        "expected_move_1sd": 0.056,
        "iv_rank": 29.59,
        "iv_percentile": 67.73,
        "term_structure_slope": -0.04,
        "skew_metric": -0.067,
        "days_to_earnings": 7,
        "event_flags": [],
        "raw": {},
    }
    ctx = option_context_from_dict(data)
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd == 0.056
    assert ctx.iv_rank == 29.59
    assert ctx.iv_percentile == 67.73
    assert ctx.term_structure_slope == -0.04
    assert ctx.skew_metric == -0.067
    assert ctx.days_to_earnings == 7


def test_option_context_from_dict_missing_data_graceful():
    ctx = option_context_from_dict({"symbol": "XYZ"})
    assert ctx.symbol == "XYZ"
    assert ctx.expected_move_1sd is None
    assert ctx.iv_rank is None
    assert ctx.event_flags == []


def test_option_context_from_dict_empty_symbol():
    ctx = option_context_from_dict({})
    assert ctx.symbol == ""


# --- Provider get_option_context: parsing and missing data ---


def test_get_option_context_empty_symbol():
    provider = OratsOptionsChainProvider()
    ctx = provider.get_option_context("")
    assert ctx.symbol == ""
    assert ctx.expected_move_1sd is None
    assert ctx.raw == {}


def test_get_option_context_summaries_parsed():
    provider = OratsOptionsChainProvider()
    summaries = [
        {
            "impliedMove": 0.0560511,
            "iv30d": 0.177298,
            "iv90d": 0.22076,
            "skewing": -0.0670888,
        }
    ]
    with patch.object(provider._client, "get_summaries", return_value=summaries):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd == pytest.approx(0.0560511)
    assert ctx.term_structure_slope == pytest.approx(0.177298 - 0.22076)
    assert ctx.skew_metric == pytest.approx(-0.0670888)
    assert "summaries" in ctx.raw


def test_get_option_context_iv_rank_parsed():
    provider = OratsOptionsChainProvider()
    ivrank = [{"ivRank1y": 29.59, "ivPct1y": 67.73}]
    with patch.object(provider._client, "get_summaries", return_value=[]):
        with patch.object(provider._client, "get_iv_rank", return_value=ivrank):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.iv_rank == 29.59
    assert ctx.iv_percentile == 67.73
    assert "ivrank" in ctx.raw


def test_get_option_context_cores_parsed():
    provider = OratsOptionsChainProvider()
    cores = [{"daysToNextErn": 14, "nextErn": "2026-02-15", "ivPctile1y": 50.0}]
    with patch.object(provider._client, "get_summaries", return_value=[]):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=cores):
                ctx = provider.get_option_context("MSFT")
    assert ctx.symbol == "MSFT"
    assert ctx.days_to_earnings == 14
    assert ctx.iv_percentile == 50.0
    assert "cores" in ctx.raw


def test_get_option_context_all_sources_combined():
    provider = OratsOptionsChainProvider()
    summaries = [
            {"impliedMove": 0.05, "iv30d": 0.20, "iv90d": 0.22, "skewing": -0.06}
    ]
    ivrank = [{"ivRank1y": 40.0, "ivPct1y": 60.0}]
    cores = [{"daysToNextErn": 7}]
    with patch.object(provider._client, "get_summaries", return_value=summaries):
        with patch.object(provider._client, "get_iv_rank", return_value=ivrank):
            with patch.object(provider._client, "get_cores", return_value=cores):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd == 0.05
    assert ctx.term_structure_slope == pytest.approx(-0.02)
    assert ctx.skew_metric == -0.06
    assert ctx.iv_rank == 40.0
    assert ctx.iv_percentile == 60.0
    assert ctx.days_to_earnings == 7


def test_get_option_context_summaries_auth_error_graceful():
    provider = OratsOptionsChainProvider()
    with patch.object(provider._client, "get_summaries", side_effect=OratsAuthError(401, "bad")):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd is None
    assert ctx.raw == {}


def test_get_option_context_summaries_value_error_graceful():
    provider = OratsOptionsChainProvider()
    with patch.object(provider._client, "get_summaries", side_effect=ValueError("rate limit")):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd is None


def test_get_option_context_summaries_empty_list():
    provider = OratsOptionsChainProvider()
    with patch.object(provider._client, "get_summaries", return_value=[]):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.symbol == "AAPL"
    assert ctx.expected_move_1sd is None
    assert ctx.term_structure_slope is None
    assert ctx.skew_metric is None


def test_get_option_context_summaries_invalid_numeric_ignored():
    provider = OratsOptionsChainProvider()
    summaries = [{"impliedMove": "bad", "iv30d": "x", "iv90d": 0.22, "skewing": None}]
    with patch.object(provider._client, "get_summaries", return_value=summaries):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert ctx.expected_move_1sd is None
    assert ctx.term_structure_slope is None  # need both iv30d and iv90d
    assert ctx.skew_metric is None


def test_get_option_context_returns_option_context_no_unhandled_exception():
    provider = OratsOptionsChainProvider()
    with patch.object(provider._client, "get_summaries", return_value=[]):
        with patch.object(provider._client, "get_iv_rank", return_value=[]):
            with patch.object(provider._client, "get_cores", return_value=[]):
                ctx = provider.get_option_context("AAPL")
    assert isinstance(ctx, OptionContext)
    assert ctx.symbol == "AAPL"
