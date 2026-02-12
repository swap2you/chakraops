# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 3.3.5: Option type normalization (PUT/CALL) for LIVE + DELAYED."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core.options.chain_provider import OptionType
from app.core.options.orats_chain_provider import normalize_put_call, OratsChainProvider


# ---------------------------------------------------------------------------
# normalize_put_call
# ---------------------------------------------------------------------------

def test_normalize_put_call_put_lower():
    """normalize_put_call('put') returns PUT."""
    assert normalize_put_call("put") == OptionType.PUT


def test_normalize_put_call_put_with_whitespace():
    """normalize_put_call(' Put ') returns PUT."""
    assert normalize_put_call(" Put ") == OptionType.PUT


def test_normalize_put_call_p():
    """normalize_put_call('p') returns PUT."""
    assert normalize_put_call("p") == OptionType.PUT


def test_normalize_put_call_call_upper():
    """normalize_put_call('CALL') returns CALL."""
    assert normalize_put_call("CALL") == OptionType.CALL


def test_normalize_put_call_c():
    """normalize_put_call('c') returns CALL."""
    assert normalize_put_call("c") == OptionType.CALL


def test_normalize_put_call_puts():
    """normalize_put_call('PUTS') returns PUT."""
    assert normalize_put_call("PUTS") == OptionType.PUT


def test_normalize_put_call_calls():
    """normalize_put_call('CALLS') returns CALL."""
    assert normalize_put_call("CALLS") == OptionType.CALL


def test_normalize_put_call_none():
    """normalize_put_call(None) returns None."""
    assert normalize_put_call(None) is None


def test_normalize_put_call_unknown_returns_none():
    """normalize_put_call('X') returns None."""
    assert normalize_put_call("X") is None


# ---------------------------------------------------------------------------
# DELAYED: _enriched_to_option_contract mapping
# ---------------------------------------------------------------------------

def test_delayed_enriched_option_type_put_lower_maps_to_put():
    """EnrichedContract with option_type='put' results in OptionType.PUT."""
    exp = date.today() + timedelta(days=40)
    ec = SimpleNamespace(
        option_type="put",
        expiration=exp,
        strike=500.0,
        bid=1.0,
        ask=1.1,
        mid=1.05,
        delta=0.25,
        open_interest=100,
        volume=10,
        dte=40,
    )
    provider = OratsChainProvider(chain_source="DELAYED")
    oc = provider._enriched_to_option_contract(ec, "SPY")
    assert oc.option_type == OptionType.PUT
    assert oc.symbol == "SPY"
    assert oc.strike == 500.0


def test_delayed_enriched_option_type_put_whitespace_maps_to_put():
    """EnrichedContract with option_type=' Put ' results in OptionType.PUT."""
    exp = date.today() + timedelta(days=40)
    ec = SimpleNamespace(
        option_type=" Put ",
        expiration=exp,
        strike=500.0,
        bid=1.0,
        ask=1.1,
        mid=1.05,
        delta=0.25,
        open_interest=100,
        volume=10,
        dte=40,
    )
    provider = OratsChainProvider(chain_source="DELAYED")
    oc = provider._enriched_to_option_contract(ec, "SPY")
    assert oc.option_type == OptionType.PUT


def test_delayed_enriched_option_type_call_maps_to_call():
    """EnrichedContract with option_type='call' results in OptionType.CALL."""
    exp = date.today() + timedelta(days=40)
    ec = SimpleNamespace(
        option_type="call",
        expiration=exp,
        strike=500.0,
        bid=1.0,
        ask=1.1,
        mid=1.05,
        delta=0.25,
        open_interest=100,
        volume=10,
        dte=40,
    )
    provider = OratsChainProvider(chain_source="DELAYED")
    oc = provider._enriched_to_option_contract(ec, "SPY")
    assert oc.option_type == OptionType.CALL
