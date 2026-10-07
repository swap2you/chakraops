# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.0: Portfolio-aware position sizing — deterministic, safe codes only, no FAIL_/WARN_."""

from __future__ import annotations

import json
from unittest.mock import patch


def test_compute_available_budget_respects_reserve() -> None:
    """Given snapshot with cash and reserve rule, compute available budget."""
    from app.core.portfolio.sizing_r260 import compute_available_budget

    snapshot = {"cash": 50_000, "total_equity": 100_000, "symbol_notionals": {}}
    config = {"MIN_CASH_RESERVE_PCT": 25.0}
    budget = compute_available_budget(snapshot, config)
    # reserve = 25% of 100k = 25k; available = 50k - 25k = 25k
    assert budget == 25_000.0

    config2 = {"MIN_CASH_RESERVE_PCT": 60.0}
    budget2 = compute_available_budget(snapshot, config2)
    assert budget2 == 0.0  # 50k - 60k reserve -> 0


def test_max_symbol_budget_enforces_cap() -> None:
    """Given existing symbol exposure, enforce symbol cap."""
    from app.core.portfolio.sizing_r260 import max_symbol_budget

    snapshot = {"total_equity": 100_000, "symbol_notionals": {"AAPL": 10_000}}
    config = {"MAX_NOTIONAL_PER_SYMBOL_PCT": 15.0}
    # max allowed = 15k; current = 10k; additional = 5k
    assert max_symbol_budget(snapshot, config, "AAPL") == 5_000.0
    assert max_symbol_budget(snapshot, config, "NVDA") == 15_000.0  # new symbol
    snapshot_over = {"total_equity": 100_000, "symbol_notionals": {"AAPL": 16_000}}
    assert max_symbol_budget(snapshot_over, config, "AAPL") == 0.0


def test_size_csp_entry_deterministic() -> None:
    """CSP contracts from strike notional; 0 when cap too low."""
    from app.core.portfolio.sizing_r260 import size_csp_entry

    assert size_csp_entry(100.0, 100.0, 25_000) == 2  # 2 * 100 * 100 = 20k
    assert size_csp_entry(100.0, 100.0, 5_000) == 0
    assert size_csp_entry(None, 50.0, 10_000) == 2  # 2 * 50 * 100 = 10k


def test_size_cc_entry_from_shares() -> None:
    """CC contracts = floor(shares/100), capped by options slots."""
    from app.core.portfolio.sizing_r260 import size_cc_entry

    assert size_cc_entry(250, 100) == 2
    assert size_cc_entry(250, 100, max_contracts_cap=1) == 1
    assert size_cc_entry(99, 100) == 0


def test_size_shares_entry() -> None:
    """Shares qty from price and budget."""
    from app.core.portfolio.sizing_r260 import size_shares_entry

    assert size_shares_entry(100.0, 10_000) == 100
    assert size_shares_entry(100.0, 0) == 0
    assert size_shares_entry(0, 10_000) == 0


def test_apply_sizing_blocked_when_at_caps() -> None:
    """When at position/symbol caps, sizing returns blocked."""
    from app.core.portfolio.sizing_r260 import apply_sizing, CONSTRAINT_MAX_OPTIONS_POSITIONS

    snapshot = {"cash": 100_000, "total_equity": 100_000, "symbol_notionals": {}}
    metrics = {
        "open_options_count": 6,
        "open_shares_count": 0,
        "symbols_exposure_count": 5,
        "total_equity": 100_000,
        "symbol_notionals": {},
    }
    config = {"MAX_OPEN_OPTIONS_POSITIONS": 6, "MIN_CASH_RESERVE_PCT": 25}
    candidate = {"symbol": "AAPL", "strategy": "CSP", "strike": 100, "underlying_price": 100}
    out = apply_sizing(candidate, snapshot, metrics, config)
    assert out["blocked"] is True
    assert CONSTRAINT_MAX_OPTIONS_POSITIONS in (out.get("sizing_constraints_hit") or [])
    assert out.get("recommended_contracts") == 0 or out.get("recommended_contracts") is None


def test_apply_sizing_shares_returns_qty() -> None:
    """Shares ENTRY gets recommended_qty and notional."""
    from app.core.portfolio.sizing_r260 import apply_sizing

    snapshot = {"cash": 80_000, "total_equity": 100_000, "symbol_notionals": {}}
    metrics = {"open_options_count": 0, "open_shares_count": 0, "symbols_exposure_count": 0, "total_equity": 100_000, "symbol_notionals": {}}
    config = {"MIN_CASH_RESERVE_PCT": 25, "MAX_NOTIONAL_PER_SYMBOL_PCT": 15}
    candidate = {"symbol": "SPY", "strategy": "SHARES", "price": 500}
    out = apply_sizing(candidate, snapshot, metrics, config)
    assert out["blocked"] is False
    assert out.get("recommended_qty") is not None and out["recommended_qty"] >= 0
    assert out.get("recommended_notional_usd") is not None or out["recommended_qty"] == 0
    assert out.get("sizing_recommended_by") == "r260"


def test_apply_sizing_no_fail_warn_in_output() -> None:
    """JSON output contains no FAIL_/WARN_ substrings."""
    from app.core.portfolio.sizing_r260 import apply_sizing

    snapshot = {"cash": 50_000, "total_equity": 100_000, "symbol_notionals": {}}
    metrics = {"open_options_count": 0, "open_shares_count": 0, "symbols_exposure_count": 0, "total_equity": 100_000, "symbol_notionals": {}}
    out = apply_sizing({"symbol": "X", "strategy": "SHARES", "price": 10}, snapshot, metrics)
    raw = json.dumps(out)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw


def test_action_needed_no_fail_warn_and_sizing_structure() -> None:
    """Action-needed response: no FAIL_/WARN_; ENTRY items with sizing_recommended_by r260 have recommended_contracts or recommended_qty."""
    from fastapi.testclient import TestClient
    from app.api.server import app

    with patch("app.api.ui_routes._require_ui_key"):
        client = TestClient(app)
        r = client.get("/api/ui/action-needed")
    assert r.status_code == 200
    data = r.json()
    raw = json.dumps(data)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw
    for key in ("options", "shares", "top_options", "top_shares"):
        if key in data and isinstance(data[key], list):
            for item in data[key]:
                if item.get("next_action_code") == "ENTRY" and item.get("sizing_recommended_by") == "r260":
                    assert "recommended_contracts" in item or "recommended_qty" in item
