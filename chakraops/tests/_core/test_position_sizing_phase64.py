# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 6.4: Position sizing (informational only). No decision impact."""

from __future__ import annotations

import pytest

from app.core.scoring.position_sizing import compute_position_sizing
from app.core.scoring.config import ACCOUNT_EQUITY_DEFAULT, MAX_NOTIONAL_PCT_PER_TRADE, MAX_CONTRACTS_PER_SYMBOL


def test_csp_sizing_stage2_strike_known():
    """CSP with stage2 strike: account 150k, strike 200 -> capital_per_contract 20k; budget 30k -> contracts_suggested = 1."""
    st2 = {"selected_trade": {"strike": 200}}
    out = compute_position_sizing("CSP", 205.0, st2, 150_000, holdings_shares=None)
    assert out["mode"] == "CSP"
    assert out["inputs"]["strike_used"] == 200
    assert out["inputs"]["strike_source"] == "stage2"
    capital_per_contract = 200 * 100
    assert capital_per_contract == 20_000
    per_trade_budget = 150_000 * MAX_NOTIONAL_PCT_PER_TRADE
    assert per_trade_budget == 30_000
    assert out["contracts_suggested"] >= 1
    assert out["capital_required_estimate"] == out["contracts_suggested"] * 20_000
    assert out["limiting_factor"] in ("NONE", "POLICY_LIMIT", "CAPITAL_LIMIT")


def test_csp_sizing_expensive_stock():
    """CSP with expensive stock (strike 1000): contracts_suggested 0 or 1; correct limiting_factor."""
    st2 = {"selected_trade": {"strike": 1000}}
    out = compute_position_sizing("CSP", 1005.0, st2, 150_000)
    assert out["mode"] == "CSP"
    assert out["contracts_max_by_capital"] <= 2
    assert out["contracts_suggested"] in (0, 1)
    if out["contracts_suggested"] == 0:
        assert out["limiting_factor"] in ("CAPITAL_LIMIT", "NO_STAGE2")
    else:
        assert out["limiting_factor"] in ("CAPITAL_LIMIT", "POLICY_LIMIT", "NONE")


def test_csp_fallback_to_spot_when_no_stage2():
    """CSP with no stage2: strike_source='spot_estimate'."""
    out = compute_position_sizing("CSP", 100.0, None, 150_000)
    assert out["mode"] == "CSP"
    assert out["inputs"]["strike_source"] == "spot_estimate"
    assert out["inputs"]["strike_used"] == 100.0


def test_cc_sizing_holdings():
    """CC with holdings 350 -> contracts_max_by_holdings=3; suggested <= MAX_CONTRACTS_PER_SYMBOL."""
    out = compute_position_sizing("CC", 50.0, {"selected_trade": {"strike": 55}}, 150_000, holdings_shares=350)
    assert out["mode"] == "CC"
    assert out["contracts_suggested"] == 3
    assert out["limiting_factor"] == "HOLDINGS_LIMIT"
    assert out["capital_required_estimate"] == 0.0


def test_cc_sizing_zero_holdings():
    """CC with holdings 0 -> contracts_suggested=0, HOLDINGS_LIMIT."""
    out = compute_position_sizing("CC", 50.0, {}, 150_000, holdings_shares=0)
    assert out["mode"] == "CC"
    assert out["contracts_suggested"] == 0
    assert out["limiting_factor"] == "HOLDINGS_LIMIT"


def test_mode_none_contracts_zero():
    """mode NONE -> contracts_suggested=0, limiting_factor=MODE_NONE."""
    out = compute_position_sizing("NONE", 100.0, {}, 150_000)
    assert out["mode"] == "NONE"
    assert out["contracts_suggested"] == 0
    assert out["limiting_factor"] == "MODE_NONE"
    assert out["capital_required_estimate"] == 0.0


def test_no_decision_impact():
    """Sizing does not mutate mode_decision or stage2 selected contract."""
    el_mode = "CSP"
    st2 = {"selected_trade": {"strike": 200}}
    out = compute_position_sizing(el_mode, 205.0, st2, 150_000)
    assert el_mode == "CSP"
    assert st2["selected_trade"]["strike"] == 200
    assert "contracts_suggested" in out
    assert "limiting_factor" in out
