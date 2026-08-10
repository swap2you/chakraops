# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""R38 — manual plan builder."""

from app.core.decision_engine.wheel_v2.manual_plan import build_manual_plan


def test_manual_plan_csp_breakeven_and_collateral():
    plan = build_manual_plan(
        strategy="CSP",
        action="OPEN_CSP",
        strike=100.0,
        expiry="2026-12-18",
        dte=35,
        delta=0.22,
        premium=1.5,
        contracts=2,
        earnings_days=40,
        profile={"profit_management": {"take_profit_pct": 50.0, "roll_at_dte": 21}},
        assignment_plan="CC_ENTRY if assigned",
        sources=["test"],
    )
    d = plan.to_dict()
    assert d["breakeven"] == 98.5  # strike - premium
    assert d["collateral"] == 20000.0  # 100 * 100 * 2
    assert d["profit_target_pct"] == 50.0
    assert d["roll_dte"] == 21
    assert d["as_of_utc"]
    assert "test" in d["sources"]
    assert d["summary_label"]


def test_manual_plan_cc_breakeven():
    plan = build_manual_plan(strategy="CC", strike=150.0, premium=2.0, contracts=1)
    assert plan.breakeven == 152.0


def test_manual_plan_shares_tranches():
    plan = build_manual_plan(
        strategy="SHARES",
        action="OPEN_SHARES",
        shares=100,
        staged_tranches=[{"tranche": 1, "shares": 50}, {"tranche": 2, "shares": 50}],
        thesis_failure_plan="Exit on support break",
    )
    assert plan.quantity == 100
    assert plan.staged_tranches and len(plan.staged_tranches) == 2
    assert plan.thesis_failure_plan
