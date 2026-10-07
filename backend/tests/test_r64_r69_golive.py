# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R64–R69 unit tests."""

from __future__ import annotations

from app.core.broker.runtime_status_r64 import classify_broker_runtime_status, sizing_allowed_for_broker
from app.core.portfolio.risk_r66 import compute_account_risk, hedge_scenario
from app.core.universe.universe_v4_r67 import evaluate_candidate_v4
from app.core.strategy.builder_r68 import build_strategy_plan, csp_payoff
from app.core.backtest.calibration_r69 import label_regime, propose_calibration_change


def test_r64_unauth_blocks_sizing():
    st = classify_broker_runtime_status(token_present=False)
    assert st["status"] == "UNAUTHENTICATED"
    assert sizing_allowed_for_broker(st) is False


def test_r64_stale_blocks_sizing():
    st = classify_broker_runtime_status(token_present=True, snapshot={"stale": True})
    assert st["status"] == "STALE"
    assert sizing_allowed_for_broker(st) is False


def test_r66_no_cross_account_pooling():
    out = compute_account_risk(
        [
            {"alias": "acct_individual", "cash": 1000, "buying_power": 2000, "equity": 5000},
            {"alias": "acct_ira_roth", "cash": 500, "buying_power": 500, "equity": 1500},
            {"alias": "acct_agentic", "cash": 0, "buying_power": 0, "equity": 0},
        ]
    )
    assert out["cross_account_collateral_pooling"] is False
    assert out["agentic_execution"] is False
    assert out["accounts"]["acct_agentic"]["csp_collateral_budget"] == 0.0
    h = hedge_scenario(portfolio_equity=100000, hedge_pct=0.1, put_cost_pct=0.02)
    assert h["trade_execution"] is False
    assert h["estimated_put_cost"] == 200.0


def test_r67_event_gate():
    out = evaluate_candidate_v4(
        {"symbol": "NVDA", "has_options": True, "liquidity_rank": 10, "strategy_family": "wheel"},
        events=[{"symbol": "NVDA", "event_type": "earnings", "within_days": 3, "source": "orats"}],
    )
    assert out["state"] == "QUARANTINE"
    assert out["threshold_retune"] is False


def test_r68_builder_and_payoff():
    plan = build_strategy_plan(capital=0, account_alias="acct_individual", horizon_months=12, max_drawdown_pct=10)
    assert plan["primary_recommendation"] == "Stay in Cash"
    assert plan["return_guarantee"] is False
    pay = csp_payoff(strike=100, credit=1.5, spot=100)
    assert pay["breakeven"] == 98.5
    assert pay["max_profit"] == 150.0


def test_r69_calibration_not_auto_applied():
    prop = propose_calibration_change(
        parameter="min_iv_rank",
        current_value=20,
        proposed_value=25,
        evidence_refs=["walk_forward_2022"],
    )
    assert prop["auto_applied"] is False
    lab = label_regime("2008-01-01", "2009-01-01", proxy=True)
    assert "50–60" in lab["disclaimer"] or "50-60" in lab["disclaimer"]
