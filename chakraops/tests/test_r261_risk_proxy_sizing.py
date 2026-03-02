# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R26.1: CSP risk proxy + cash-secured reserve — deterministic, safe codes only."""

from __future__ import annotations

import json


def test_cash_secured_committed_calculation() -> None:
    """Cash-secured committed = sum(CSP strike * 100 * contracts)."""
    from app.core.portfolio.sizing_r260 import compute_cash_secured_committed

    snapshot = {
        "option_positions": [
            {"symbol": "AAPL", "strategy": "CSP", "contracts": 2, "strike": 150.0},
            {"symbol": "NVDA", "strategy": "CC", "contracts": 1, "strike": 200.0},
            {"symbol": "SPY", "strategy": "CSP", "contracts": 1, "strike": 500.0},
        ],
    }
    committed = compute_cash_secured_committed(snapshot)
    # 2*150*100 + 1*500*100 = 30000 + 50000 = 80000 (CC ignored)
    assert committed == 80_000.0


def test_csp_size_zero_when_committed_plus_reserve_exceeds_cash() -> None:
    """CSP sizing goes to 0 when available_cash_for_new_csp <= 0."""
    from app.core.portfolio.sizing_r260 import (
        apply_sizing,
        compute_available_cash_for_new_csp,
        CONSTRAINT_CASH_SECURED,
    )

    # Cash 50k, committed 40k, reserve 25% of 100k = 25k -> available = 50 - 40 - 25 = -15 -> 0
    snapshot = {
        "cash": 50_000,
        "total_equity": 100_000,
        "option_positions": [
            {"symbol": "AAPL", "strategy": "CSP", "contracts": 2, "strike": 200.0},
        ],
        "symbol_notionals": {},
    }
    cfg = {"MIN_CASH_RESERVE_PCT": 25.0}
    available = compute_available_cash_for_new_csp(snapshot, cfg)
    assert available == 0.0

    metrics = {
        "open_options_count": 0,
        "open_shares_count": 0,
        "symbols_exposure_count": 0,
        "total_equity": 100_000,
        "symbol_notionals": {},
    }
    candidate = {"symbol": "SPY", "strategy": "CSP", "strike": 450, "underlying_price": 450}
    out = apply_sizing(candidate, snapshot, metrics, cfg)
    assert out["blocked"] is True
    assert CONSTRAINT_CASH_SECURED in (out.get("sizing_constraints_hit") or [])


def test_risk_proxy_uses_snapshot_only_deterministic() -> None:
    """Risk proxy estimate uses symbol_context only; deterministic."""
    from app.core.portfolio.risk_proxy_r261 import (
        estimate_downside_move_pct,
        estimate_csp_max_loss_proxy,
        cap_contracts_by_risk_budget,
        DEFAULT_DOWNSIDE_MOVE_PCT,
    )

    # No context -> default
    assert estimate_downside_move_pct({}) == DEFAULT_DOWNSIDE_MOVE_PCT
    # Earnings within 14 days with implied move
    ctx = {"earnings_days": 7, "implied_earnings_move_pct": 5.0}
    assert estimate_downside_move_pct(ctx) == 5.0
    # ATR proxy
    ctx2 = {"atr_pct": 2.0}
    assert estimate_downside_move_pct(ctx2) == 3.0  # 2 * 1.5

    # Loss proxy and cap (allow float tolerance; cap uses floor so 700/700 can be <1 due to float)
    assert abs(estimate_csp_max_loss_proxy(100.0, 1, 7.0) - 700.0) < 1.0  # 100 * 0.07 * 100
    assert cap_contracts_by_risk_budget(701.0, 100.0, 7.0) >= 1
    assert cap_contracts_by_risk_budget(500.0, 100.0, 7.0) == 0


def test_enforcement_flag_toggles_behavior() -> None:
    """When CSP_RISK_PROXY_ENFORCE=true, contracts capped by risk proxy."""
    from app.core.portfolio.sizing_r260 import apply_sizing

    # Use strike 120 so symbol_budget (35% of 200k = 70k) allows 5 contracts; risk cap 2% of 200k = 4k,
    # loss per contract 120*0.07*100 = 840 -> cap 4. So without enforce 5, with enforce min(5, 4) = 4.
    snapshot = {
        "cash": 200_000,
        "total_equity": 200_000,
        "option_positions": [],
        "symbol_notionals": {},
    }
    metrics = {
        "open_options_count": 0,
        "open_shares_count": 0,
        "symbols_exposure_count": 0,
        "total_equity": 200_000,
        "symbol_notionals": {},
    }
    cfg_adv = {
        "MIN_CASH_RESERVE_PCT": 25,
        "CSP_RISK_PROXY_ENFORCE": False,
        "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0,
        "MAX_NOTIONAL_PER_SYMBOL_PCT": 35.0,
    }
    candidate = {"symbol": "SPY", "strategy": "CSP", "strike": 120, "underlying_price": 120}
    out_adv = apply_sizing(candidate, snapshot, metrics, cfg_adv)
    assert out_adv["blocked"] is False
    contracts_adv = out_adv.get("recommended_contracts") or 0
    assert contracts_adv >= 1
    cap_adv = out_adv.get("csp_risk_proxy_cap_contracts")
    assert cap_adv is not None

    cfg_enforce = {
        "MIN_CASH_RESERVE_PCT": 25,
        "CSP_RISK_PROXY_ENFORCE": True,
        "OPTIONS_MAX_RISK_PER_TRADE_PCT": 2.0,
        "MAX_NOTIONAL_PER_SYMBOL_PCT": 35.0,
    }
    out_enforce = apply_sizing(candidate, snapshot, metrics, cfg_enforce)
    assert out_enforce["csp_risk_proxy_enforced"] is True
    assert (out_enforce.get("recommended_contracts") or 0) <= (out_enforce.get("csp_risk_proxy_cap_contracts") or 0)


def test_output_json_no_fail_warn() -> None:
    """Sizing and risk proxy output contain no FAIL_/WARN_ substrings."""
    from app.core.portfolio.sizing_r260 import apply_sizing
    from app.core.portfolio.risk_proxy_r261 import estimate_downside_move_pct, estimate_csp_max_loss_proxy

    snapshot = {"cash": 100_000, "total_equity": 100_000, "option_positions": [], "symbol_notionals": {}}
    metrics = {"open_options_count": 0, "open_shares_count": 0, "symbols_exposure_count": 0, "total_equity": 100_000, "symbol_notionals": {}}
    out = apply_sizing(
        {"symbol": "AAPL", "strategy": "CSP", "strike": 150, "underlying_price": 150},
        snapshot,
        metrics,
    )
    raw = json.dumps(out)
    assert "FAIL_" not in raw
    assert "WARN_" not in raw

    # Risk proxy returns numeric only
    assert "FAIL" not in str(estimate_downside_move_pct({}))
    assert "WARN" not in str(estimate_csp_max_loss_proxy(100, 1, 7.0))
