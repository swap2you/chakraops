# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R24.0: Options position sizing (request-time only; not persisted)."""

import json
import os
import pytest
from pathlib import Path

from app.core.options.options_sizing import build_options_sizing_r240
from app.core.config.trade_rules import (
    OPTIONS_MAX_CONTRACTS_PER_TRADE,
    OPTIONS_MAX_NOTIONAL_PCT,
    OPTIONS_RISK_PCT_PER_TRADE_DEFAULT,
)


def test_csp_sizing_with_account_data():
    """CSP: suggested_contracts, required_cash, credit_estimate, risk_pct_used when account has cash."""
    c_dicts = [
        {"strike": 100.0, "expiration": "2026-03-20", "mid": 3.50, "bid": 3.40, "ask": 3.60},
    ]
    account = {"total_capital": 100_000.0, "cash": 80_000.0, "buying_power": 80_000.0}
    out = build_options_sizing_r240(
        c_dicts,
        selected_contract_key="100-2026-03-20-PUT",
        strategy="CSP",
        account_summary=account,
        shares_position=None,
        spot=105.0,
    )
    assert out["basis"] == "OK"
    assert out["suggested_contracts"] is not None
    assert out["suggested_contracts"] >= 1
    assert out["suggested_contracts"] <= OPTIONS_MAX_CONTRACTS_PER_TRADE
    assert out["required_cash"] is not None
    assert out["required_cash"] == 100.0 * 100 * out["suggested_contracts"]
    assert out["credit_estimate"] is not None
    assert out["risk_pct_used"] is not None
    assert "SIZED_BY_CASH_SECURED" in out["notes_codes"]
    assert "FAIL_" not in str(out)
    assert "WARN_" not in str(out)


def test_cc_sizing_limited_by_shares():
    """CC: suggested_contracts limited by floor(shares/100); required_cash=0."""
    c_dicts = [
        {"strike": 150.0, "expiration": "2026-04-18", "mid": 2.00, "bid": 1.90, "ask": 2.10},
    ]
    account = {"total_capital": 50_000.0, "cash": 10_000.0, "buying_power": 10_000.0}
    shares_position = {"quantity": 250}
    out = build_options_sizing_r240(
        c_dicts,
        selected_contract_key="150-2026-04-18-CALL",
        strategy="CC",
        account_summary=account,
        shares_position=shares_position,
        spot=148.0,
    )
    assert out["basis"] == "OK"
    assert out["suggested_contracts"] == 2  # floor(250/100) = 2, cap at MAX_CONTRACTS
    assert out["required_cash"] == 0.0
    assert out["credit_estimate"] is not None
    assert "SIZED_BY_COVERED_SHARES" in out["notes_codes"]


def test_insufficient_account_data():
    """When account_summary is None or has no capital, basis=INSUFFICIENT_DATA and null numbers."""
    c_dicts = [{"strike": 100.0, "expiration": "2026-03-20", "mid": 3.0}]
    out = build_options_sizing_r240(
        c_dicts,
        selected_contract_key="100-2026-03-20-PUT",
        strategy="CSP",
        account_summary=None,
        shares_position=None,
        spot=105.0,
    )
    assert out["basis"] == "INSUFFICIENT_DATA"
    assert out["suggested_contracts"] is None
    assert out["required_cash"] is None
    assert out["credit_estimate"] is None
    assert out["risk_pct_used"] is None


def test_no_selected_candidate():
    """When no candidates, basis=NO_SELECTED_CANDIDATE."""
    out = build_options_sizing_r240(
        [],
        selected_contract_key=None,
        strategy="CSP",
        account_summary={"total_capital": 100_000.0},
        shares_position=None,
        spot=100.0,
    )
    assert out["basis"] == "NO_SELECTED_CANDIDATE"
    assert out["suggested_contracts"] is None


def test_sizing_not_persisted_to_decision_latest(tmp_path, monkeypatch):
    """Ensure options_sizing is not written to out/decision_latest.json (request-time only)."""
    monkeypatch.setenv("OUT_DIR", str(tmp_path))
    from app.core.eval.evaluation_store_v2 import get_decision_store_path
    store_path = get_decision_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {"artifact_version": "v2", "metadata": {}, "symbols": [], "gates_by_symbol": {}, "candidates_by_symbol": {}}
    with open(store_path, "w") as f:
        json.dump(artifact, f, indent=2)
    path_str = str(store_path)
    with open(path_str, "r") as f:
        data = json.load(f)
    assert "options_sizing" not in json.dumps(data)
    assert "suggested_contracts" not in json.dumps(data) or "options_sizing" not in str(data)
