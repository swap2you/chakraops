# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Tests for Phase 5 options-layer contract selection."""

from datetime import date, timedelta
from typing import Any, Dict, List

import pytest

from app.core.options.contract_selector import (
    select_csp_contract,
    select_cc_contract,
    ContractResult,
)


class MockChainProvider:
    """Synthetic chain for tests. get_expirations(symbol) -> list[date]; get_chain(symbol, expiry, right) -> list[dict]."""

    def __init__(
        self,
        expirations: List[date],
        puts: Dict[date, List[Dict[str, Any]]],
        calls: Dict[date, List[Dict[str, Any]]],
    ) -> None:
        self.expirations = expirations
        self.puts = puts
        self.calls = calls

    def get_expirations(self, symbol: str) -> List[date]:
        return list(self.expirations)

    def get_chain(self, symbol: str, expiry: date, right: str) -> List[Dict[str, Any]]:
        if (right or "").upper() == "P":
            return list(self.puts.get(expiry, []))
        return list(self.calls.get(expiry, []))


def test_csp_chain_unavailable():
    class EmptyProvider:
        def get_expirations(self, symbol: str):
            return []

        def get_chain(self, symbol, expiry, right):
            return []

    r = select_csp_contract("SPY", {"price": 450.0, "iv_rank": 25, "regime": "RISK_ON"}, EmptyProvider(), None)
    assert r.eligible is False
    assert "chain_unavailable" in r.rejection_reasons


def test_csp_no_expiry_in_dte_window():
    today = date.today()
    # Expirations all outside 30–45 DTE
    expirations = [today + timedelta(days=10), today + timedelta(days=60)]
    provider = MockChainProvider(expirations, {}, {})
    cfg = {"csp_min_dte": 30, "csp_max_dte": 45, "csp_delta_min": 0.25, "csp_delta_max": 0.35}
    r = select_csp_contract("SPY", {"price": 450.0, "iv_rank": 25, "regime": "RISK_ON"}, provider, cfg)
    assert r.eligible is False
    assert "no_expiry_in_dte_window" in r.rejection_reasons


def test_csp_no_put_in_delta_range():
    today = date.today()
    exp = today + timedelta(days=35)
    # Puts with delta outside [-0.35, -0.25]
    puts = {
        exp: [
            {"strike": 440, "bid": 4, "ask": 4.5, "delta": -0.10, "iv": 0.22},
            {"strike": 430, "bid": 3, "ask": 3.5, "delta": -0.08, "iv": 0.21},
        ]
    }
    provider = MockChainProvider([exp], puts, {})
    cfg = {"csp_min_dte": 30, "csp_max_dte": 45, "csp_delta_min": 0.25, "csp_delta_max": 0.35, "max_spread_pct": 20, "min_roc": 0.005}
    r = select_csp_contract("SPY", {"price": 450.0, "iv_rank": 25, "regime": "RISK_ON"}, provider, cfg)
    assert r.eligible is False
    assert "no_put_in_delta_range" in r.rejection_reasons


def test_csp_tie_breaker_closest_delta_then_higher_strike():
    today = date.today()
    exp = today + timedelta(days=35)
    # Two puts in delta range; one closer to -0.25, one higher strike
    puts = {
        exp: [
            {"strike": 430, "bid": 4, "ask": 4.2, "delta": -0.28, "iv": 0.22},
            {"strike": 435, "bid": 4.5, "ask": 4.8, "delta": -0.26, "iv": 0.22},
            {"strike": 440, "bid": 5, "ask": 5.2, "delta": -0.26, "iv": 0.22},
        ]
    }
    provider = MockChainProvider([exp], puts, {})
    cfg = {"csp_min_dte": 30, "csp_max_dte": 45, "csp_delta_min": 0.25, "csp_delta_max": 0.35, "max_spread_pct": 20, "min_roc": 0.005, "min_oi": 0, "min_volume": 0}
    r = select_csp_contract("SPY", {"price": 450.0, "iv_rank": 25, "regime": "RISK_ON"}, provider, cfg)
    assert r.eligible is True
    assert r.chosen_contract is not None
    # Target delta -0.25; -0.26 is closer than -0.28; of -0.26 and -0.26, higher strike wins -> 440
    assert r.chosen_contract["strike"] == 440
    assert r.chosen_contract["delta"] == -0.26
    assert r.roc is not None
    assert r.dte == 35


def test_csp_spread_too_wide_rejected():
    today = date.today()
    exp = today + timedelta(days=35)
    puts = {
        exp: [
            {"strike": 435, "bid": 4, "ask": 6, "delta": -0.26, "iv": 0.22},
        ]
    }
    provider = MockChainProvider([exp], puts, {})
    cfg = {"csp_min_dte": 30, "csp_max_dte": 45, "csp_delta_min": 0.25, "csp_delta_max": 0.35, "max_spread_pct": 5.0, "min_roc": 0.005}
    r = select_csp_contract("SPY", {"price": 450.0, "iv_rank": 25, "regime": "RISK_ON"}, provider, cfg)
    assert r.eligible is False
    # spread = 2, mid = 5 -> 40% > 5% so rejected (we don't have a specific "spread_too_wide" in our code yet - we skip in filter)
    # So the only put has spread_pct 40, we filter it out, and we get no_put_in_delta_range because no candidates left
    assert "no_put_in_delta_range" in r.rejection_reasons


def test_cc_no_shares_held():
    today = date.today()
    exp = today + timedelta(days=35)
    calls = {exp: [{"strike": 460, "bid": 4, "ask": 4.2, "delta": 0.28, "iv": 0.22}]}
    provider = MockChainProvider([exp], {}, calls)
    cfg = {"cc_min_dte": 30, "cc_max_dte": 45, "cc_delta_min": 0.15, "cc_delta_max": 0.35, "max_spread_pct": 20, "min_roc": 0.005}
    r = select_cc_contract("SPY", {"price": 450.0}, provider, cfg, shares_held=0)
    assert r.eligible is False
    assert "no_shares_held_for_cc" in r.rejection_reasons


def test_cc_selects_call_tie_break_lower_strike():
    today = date.today()
    exp = today + timedelta(days=35)
    calls = {
        exp: [
            {"strike": 460, "bid": 4, "ask": 4.2, "delta": 0.26, "iv": 0.22},
            {"strike": 455, "bid": 4.5, "ask": 4.7, "delta": 0.26, "iv": 0.22},
        ]
    }
    provider = MockChainProvider([exp], {}, calls)
    cfg = {"cc_min_dte": 30, "cc_max_dte": 45, "cc_delta_min": 0.15, "cc_delta_max": 0.35, "max_spread_pct": 20, "min_roc": 0.005}
    r = select_cc_contract("SPY", {"price": 450.0}, provider, cfg, shares_held=100)
    assert r.eligible is True
    assert r.chosen_contract is not None
    # Same delta 0.26; tie-break for CC is lower strike (more OTM) -> 455
    assert r.chosen_contract["strike"] == 455
    assert r.chosen_contract["right"] == "C"


def test_csp_options_skipped_no_price():
    class EmptyProvider:
        def get_expirations(self, symbol): return []
        def get_chain(self, symbol, expiry, right): return []

    r = select_csp_contract("SPY", {"price": None, "iv_rank": 25}, EmptyProvider(), None)
    assert r.eligible is False
    assert "options_skipped_no_price" in r.rejection_reasons


def test_integration_smoke_mocked_provider():
    """Smoke: run CSP selection with mocked provider returns ContractResult."""
    today = date.today()
    exp = today + timedelta(days=38)
    puts = {
        exp: [
            {"strike": 445, "bid": 5, "ask": 5.2, "delta": -0.20, "iv": 0.20},
        ]
    }
    provider = MockChainProvider([exp], puts, {})
    ctx = {"price": 450.0, "iv_rank": 30, "regime": "RISK_ON", "snapshot_age_minutes": 10.0}
    r = select_csp_contract("SPY", ctx, provider, None)
    assert isinstance(r, ContractResult)
    assert r.eligible is True
    assert r.chosen_contract["strike"] == 445
    assert r.roc is not None
    assert r.dte == 38
    assert "symbol" in r.debug_inputs
