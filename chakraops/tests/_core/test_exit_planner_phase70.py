# Copyright 2026 ChakraOps
# SPDX-License-Identifier: MIT
"""Phase 7.0: Hybrid Exit Model — exit planner tests. Informational only; no trading logic."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.lifecycle.exit_planner import build_exit_plan


def test_mode_none_returns_enabled_false():
    """mode_decision NONE → enabled false, no structure."""
    plan = build_exit_plan(
        "SPY", "NONE", 450.0, {}, None, None, 150_000
    )
    assert plan["enabled"] is False
    assert plan["mode"] == "NONE"
    assert plan["premium_plan"] is None
    assert plan["structure_plan"] is None
    assert "mode_decision not CSP/CC" in (plan.get("missing_fields") or [])


def test_csp_with_valid_sr_and_atr_produces_targets_and_stop():
    """CSP with support, resistance, ATR → T1, T2, T3, stop_hint valid."""
    spot = 500.0
    support = 480.0
    resistance = 520.0
    atr14 = 4.0
    el = {
        "mode_decision": "CSP",
        "regime": "UP",
        "support_level": support,
        "resistance_level": resistance,
        "computed": {"ATR14": atr14},
    }
    st2 = {"selected_trade": {"exp": (date.today() + timedelta(days=35)).isoformat(), "dte": 35}}
    plan = build_exit_plan("SPY", "CSP", spot, el, st2, {}, 150_000)
    assert plan["enabled"] is True
    assert plan["mode"] == "CSP"
    sp = plan["structure_plan"]
    assert sp is not None
    # T1 = midpoint(spot, resistance) = (500+520)/2 = 510
    assert sp["T1"] == 510.0
    assert sp["T2"] == 520.0
    # T3 = resistance + extension = 520 + (520-500) = 540
    assert sp["T3"] == 540.0
    # stop_hint = support - ATR * 1.5 = 480 - 6 = 474
    assert sp["stop_hint_price"] == 474.0
    assert plan["time_plan"]["dte_soft_exit"] == 14
    assert plan["time_plan"]["dte_hard_exit"] == 7
    assert plan["time_plan"]["dte"] == 35


def test_cc_mirror_logic_correct():
    """CC: T1 = midpoint(spot, support), T2 = support, stop = resistance + ATR*mult."""
    spot = 500.0
    support = 470.0
    resistance = 530.0
    atr14 = 5.0
    el = {
        "mode_decision": "CC",
        "regime": "DOWN",
        "support_level": support,
        "resistance_level": resistance,
        "computed": {"ATR14": atr14},
    }
    st2 = {"selected_trade": {"exp": "2026-04-18", "dte": 45}}
    plan = build_exit_plan("SPY", "CC", spot, el, st2, {}, 150_000)
    assert plan["enabled"] is True
    assert plan["mode"] == "CC"
    sp = plan["structure_plan"]
    assert sp["T1"] == (500 + 470) / 2  # 485
    assert sp["T2"] == 470.0
    # T3 = support - extension = 470 - (500-470) = 440
    assert sp["T3"] == 440.0
    # stop_hint = resistance + ATR*1.5 = 530 + 7.5 = 537.5
    assert sp["stop_hint_price"] == 537.5


def test_missing_resistance_handled_safely_csp():
    """CSP with missing resistance → missing_fields, no crash; T1/T2/T3 None or absent."""
    el = {
        "mode_decision": "CSP",
        "regime": "UP",
        "support_level": 480.0,
        "resistance_level": None,
        "computed": {"ATR14": 4.0},
    }
    plan = build_exit_plan("SPY", "CSP", 500.0, el, {}, {}, 150_000)
    assert plan["enabled"] is True
    assert "resistance_level" in (plan.get("missing_fields") or [])
    sp = plan["structure_plan"]
    assert sp["T1"] is None
    assert sp["T2"] is None
    # stop_hint can still be set from support - ATR
    assert sp["stop_hint_price"] == 474.0  # 480 - 6


def test_dte_computed_from_expiration_when_not_in_selected_trade():
    """DTE computed from expiration date when selected_trade has exp but no dte."""
    exp_date = date.today() + timedelta(days=42)
    el = {"mode_decision": "CSP", "regime": "UP", "support_level": 100, "resistance_level": 110, "computed": {"ATR14": 1.0}}
    st2 = {"selected_trade": {"exp": exp_date.isoformat()}}  # no dte key
    plan = build_exit_plan("SPY", "CSP", 105.0, el, st2, {}, None)
    assert plan["enabled"] is True
    assert plan["time_plan"]["dte"] == 42


def test_panic_flag_triggers_on_regime_conflict_csp():
    """CSP with daily regime != UP → panic_flag True, panic_reason regime_flip."""
    el = {
        "mode_decision": "CSP",
        "regime": "DOWN",
        "support_level": 480.0,
        "resistance_level": 520.0,
        "computed": {"ATR14": 4.0},
    }
    plan = build_exit_plan("SPY", "CSP", 500.0, el, {}, {}, 150_000)
    assert plan["enabled"] is True
    assert plan["panic_plan"]["panic_flag"] is True
    assert plan["panic_plan"]["panic_reason"] == "regime_flip"


def test_panic_flag_weekly_regime_conflict_csp():
    """CSP with daily UP but weekly != UP → panic when regime_weekly present."""
    el = {
        "mode_decision": "CSP",
        "regime": "UP",
        "regime_weekly": "DOWN",
        "support_level": 480.0,
        "resistance_level": 520.0,
        "computed": {"ATR14": 4.0},
    }
    plan = build_exit_plan("SPY", "CSP", 500.0, el, {}, {}, 150_000)
    assert plan["enabled"] is True
    assert plan["panic_plan"]["panic_flag"] is True
    assert plan["panic_plan"]["panic_reason"] == "regime_flip"


def test_no_mutation_of_eligibility_or_stage2():
    """build_exit_plan does not mutate eligibility_trace or stage2_trace."""
    el = {
        "mode_decision": "CSP",
        "regime": "UP",
        "support_level": 480.0,
        "resistance_level": 520.0,
        "computed": {"ATR14": 4.0},
    }
    st2 = {"selected_trade": {"exp": "2026-04-01", "dte": 30}}
    el_id = id(el)
    st2_id = id(st2)
    plan = build_exit_plan("SPY", "CSP", 500.0, el, st2, {}, 150_000)
    assert id(el) == el_id
    assert id(st2) == st2_id
    assert el.get("mode_decision") == "CSP"
    assert st2.get("selected_trade", {}).get("dte") == 30
    # No new keys added to el/st2
    assert "exit_plan" not in el
    assert "exit_plan" not in st2
